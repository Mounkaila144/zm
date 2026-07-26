package ne.zarma.zarma_mobile

import android.app.Activity
import android.content.Intent
import android.net.Uri
import com.google.android.play.core.appupdate.AppUpdateManager
import com.google.android.play.core.appupdate.AppUpdateManagerFactory
import com.google.android.play.core.install.model.AppUpdateType
import com.google.android.play.core.install.model.UpdateAvailability
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.android.FlutterActivity
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private lateinit var updateManager: AppUpdateManager
    private var updateResult: MethodChannel.Result? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        updateManager = AppUpdateManagerFactory.create(this)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "ne.zarma.zarma_mobile/update",
        ).setMethodCallHandler(::handleUpdateCall)
    }

    private fun handleUpdateCall(call: MethodCall, result: MethodChannel.Result) {
        if (call.method != "startImmediateUpdate") {
            result.notImplemented()
            return
        }
        if (updateResult != null) {
            result.success(false)
            return
        }
        updateManager.appUpdateInfo
            .addOnSuccessListener { info ->
                val available =
                    info.updateAvailability() == UpdateAvailability.UPDATE_AVAILABLE ||
                        info.updateAvailability() ==
                        UpdateAvailability.DEVELOPER_TRIGGERED_UPDATE_IN_PROGRESS
                if (!available || !info.isUpdateTypeAllowed(AppUpdateType.IMMEDIATE)) {
                    result.success(openPlayStore(call.argument("storeUrl")))
                    return@addOnSuccessListener
                }
                updateResult = result
                @Suppress("DEPRECATION")
                updateManager.startUpdateFlowForResult(
                    info,
                    AppUpdateType.IMMEDIATE,
                    this,
                    UPDATE_REQUEST_CODE,
                )
            }
            .addOnFailureListener {
                result.success(openPlayStore(call.argument("storeUrl")))
            }
    }

    private fun openPlayStore(storeUrl: String?): Boolean {
        val marketIntent = Intent(
            Intent.ACTION_VIEW,
            Uri.parse("market://details?id=$packageName"),
        ).apply {
            setPackage("com.android.vending")
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        return try {
            startActivity(marketIntent)
            true
        } catch (_: Exception) {
            val fallbackUrl =
                storeUrl ?: "https://play.google.com/store/apps/details?id=$packageName"
            try {
                startActivity(
                    Intent(Intent.ACTION_VIEW, Uri.parse(fallbackUrl)).apply {
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    },
                )
                true
            } catch (_: Exception) {
                false
            }
        }
    }

    @Deprecated("Play Core uses the Activity result API for this flow")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == UPDATE_REQUEST_CODE) {
            updateResult?.success(resultCode == Activity.RESULT_OK)
            updateResult = null
        }
    }

    companion object {
        private const val UPDATE_REQUEST_CODE = 7102
    }
}
