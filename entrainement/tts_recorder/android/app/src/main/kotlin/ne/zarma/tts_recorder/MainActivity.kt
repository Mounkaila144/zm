package ne.zarma.tts_recorder

import android.app.Activity
import android.content.Intent
import android.media.MediaPlayer
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.ZipInputStream

class MainActivity : FlutterActivity() {
    private val channelName = "ne.zarma.tts_recorder/platform"
    private val csvRequestCode = 4107
    private val zipRequestCode = 4108
    private var pendingCsvResult: MethodChannel.Result? = null
    private var pendingZipResult: MethodChannel.Result? = null
    private var pendingZipDirectory: String? = null
    private var player: MediaPlayer? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler(::handleMethodCall)
    }

    private fun handleMethodCall(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "importCsv" -> {
                if (pendingCsvResult != null || pendingZipResult != null) {
                    result.error("FILE_PICKER_BUSY", "Un sélecteur est déjà ouvert.", null)
                    return
                }
                pendingCsvResult = result
                val intent =
                    Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "text/*"
                        putExtra(
                            Intent.EXTRA_MIME_TYPES,
                            arrayOf(
                                "text/csv",
                                "text/comma-separated-values",
                                "application/csv",
                                "text/plain",
                            ),
                        )
                    }
                startActivityForResult(
                    Intent.createChooser(intent, "Choisir un CSV de consignes"),
                    csvRequestCode,
                )
            }
            "importExampleZip" -> {
                if (pendingCsvResult != null || pendingZipResult != null) {
                    result.error("FILE_PICKER_BUSY", "Un sélecteur est déjà ouvert.", null)
                    return
                }
                val targetDirectory = call.argument<String>("targetDirectory")
                if (targetDirectory == null) {
                    result.error("ZIP_TARGET_MISSING", "Dossier cible absent.", null)
                    return
                }
                pendingZipResult = result
                pendingZipDirectory = targetDirectory
                val intent =
                    Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "application/zip"
                        putExtra(
                            Intent.EXTRA_MIME_TYPES,
                            arrayOf(
                                "application/zip",
                                "application/x-zip-compressed",
                                "application/octet-stream",
                            ),
                        )
                    }
                startActivityForResult(
                    Intent.createChooser(intent, "Choisir le ZIP des exemples"),
                    zipRequestCode,
                )
            }
            "playAudio" -> {
                val path = call.argument<String>("path")
                if (path == null || !File(path).isFile) {
                    result.error("AUDIO_MISSING", "Fichier audio introuvable.", null)
                    return
                }
                try {
                    releasePlayer()
                    player =
                        MediaPlayer().apply {
                            setDataSource(path)
                            setOnCompletionListener { releasePlayer() }
                            setOnErrorListener { _, _, _ ->
                                releasePlayer()
                                true
                            }
                            prepare()
                            start()
                        }
                    result.success(null)
                } catch (error: Exception) {
                    releasePlayer()
                    result.error("AUDIO_PLAY_ERROR", error.message, null)
                }
            }
            "stopAudio" -> {
                releasePlayer()
                result.success(null)
            }
            else -> result.notImplemented()
        }
    }

    @Deprecated("Utilisé pour rester compatible avec FlutterActivity.")
    override fun onActivityResult(
        requestCode: Int,
        resultCode: Int,
        data: Intent?,
    ) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == zipRequestCode) {
            finishZipImport(resultCode, data)
            return
        }
        if (requestCode != csvRequestCode) return
        val result = pendingCsvResult ?: return
        pendingCsvResult = null
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) {
            result.success(null)
            return
        }
        try {
            val csv =
                contentResolver.openInputStream(uri)?.bufferedReader(Charsets.UTF_8).use {
                    requireNotNull(it) { "Fichier inaccessible." }
                    it.readText()
                }
            result.success(csv)
        } catch (error: Exception) {
            result.error("CSV_READ_ERROR", error.message, null)
        }
    }

    private fun finishZipImport(
        resultCode: Int,
        data: Intent?,
    ) {
        val result = pendingZipResult ?: return
        val targetDirectory = pendingZipDirectory
        pendingZipResult = null
        pendingZipDirectory = null
        val uri = data?.data
        if (resultCode != Activity.RESULT_OK || uri == null) {
            result.success(null)
            return
        }
        if (targetDirectory == null) {
            result.error("ZIP_TARGET_MISSING", "Dossier cible absent.", null)
            return
        }
        try {
            val root = File(targetDirectory).canonicalFile
            val appData = File(applicationInfo.dataDir).canonicalFile
            require(root.path.startsWith("${appData.path}${File.separator}")) {
                "Dossier cible non autorisé."
            }
            root.mkdirs()

            var manifest: String? = null
            val files = linkedMapOf<String, String>()
            var totalBytes = 0L
            var entryCount = 0
            contentResolver.openInputStream(uri).use { input ->
                requireNotNull(input) { "ZIP inaccessible." }
                ZipInputStream(input.buffered()).use { zip ->
                    while (true) {
                        val entry = zip.nextEntry ?: break
                        if (entry.isDirectory) {
                            zip.closeEntry()
                            continue
                        }
                        entryCount += 1
                        require(entryCount <= 2000) { "ZIP trop volumineux." }
                        val normalized = entry.name.replace('\\', '/')
                        val fileName = normalized.substringAfterLast('/')
                        val bytes = readBoundedEntry(zip)
                        totalBytes += bytes.size
                        require(totalBytes <= 150L * 1024L * 1024L) {
                            "ZIP décompressé supérieur à 150 Mo."
                        }
                        when {
                            fileName.equals("manifest.csv", ignoreCase = true) -> {
                                require(manifest == null) {
                                    "Plusieurs manifests : exporter un seul locuteur."
                                }
                                manifest = bytes.toString(Charsets.UTF_8)
                            }
                            fileName.endsWith(".wav", ignoreCase = true) -> {
                                require(!files.containsKey(fileName)) {
                                    "Audio en double : $fileName"
                                }
                                val destination = File(root, fileName)
                                destination.writeBytes(bytes)
                                files[fileName] = destination.absolutePath
                            }
                        }
                        zip.closeEntry()
                    }
                }
            }
            result.success(
                mapOf(
                    "manifest" to requireNotNull(manifest) { "manifest.csv absent du ZIP." },
                    "files" to files,
                ),
            )
        } catch (error: Exception) {
            result.error("ZIP_IMPORT_ERROR", error.message, null)
        }
    }

    private fun readBoundedEntry(zip: ZipInputStream): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(16 * 1024)
        while (true) {
            val count = zip.read(buffer)
            if (count < 0) break
            output.write(buffer, 0, count)
            require(output.size() <= 20 * 1024 * 1024) {
                "Une entrée du ZIP dépasse 20 Mo."
            }
        }
        return output.toByteArray()
    }

    private fun releasePlayer() {
        player?.release()
        player = null
    }

    override fun onDestroy() {
        pendingCsvResult?.error("ACTIVITY_CLOSED", "L’application a été fermée.", null)
        pendingCsvResult = null
        pendingZipResult?.error("ACTIVITY_CLOSED", "L’application a été fermée.", null)
        pendingZipResult = null
        pendingZipDirectory = null
        releasePlayer()
        super.onDestroy()
    }
}
