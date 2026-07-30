import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

class ZipEntrySource {
  const ZipEntrySource.fromBytes(this.path, this.bytes) : file = null;
  const ZipEntrySource.fromFile(this.path, this.file) : bytes = null;

  final String path;
  final Uint8List? bytes;
  final File? file;
}

class _CentralEntry {
  const _CentralEntry({
    required this.name,
    required this.crc,
    required this.size,
    required this.offset,
  });

  final Uint8List name;
  final int crc;
  final int size;
  final int offset;
}

Future<File> writeStoredZip(
  File destination,
  List<ZipEntrySource> sources,
) async {
  final partial = File('${destination.path}.part');
  if (await partial.exists()) {
    await partial.delete();
  }
  final output = await partial.open(mode: FileMode.write);
  final central = <_CentralEntry>[];
  var position = 0;

  Future<void> writeBytes(List<int> bytes) async {
    await output.writeFrom(bytes);
    position += bytes.length;
  }

  try {
    for (final source in sources) {
      final name = Uint8List.fromList(utf8.encode(source.path));
      final content = source.bytes ?? await source.file!.readAsBytes();
      final crc = crc32(content);
      final offset = position;
      final local = BytesBuilder(copy: false)
        ..add(_u32(0x04034b50))
        ..add(_u16(20))
        ..add(_u16(0x0800))
        ..add(_u16(0))
        ..add(_u16(0))
        ..add(_u16(0))
        ..add(_u32(crc))
        ..add(_u32(content.length))
        ..add(_u32(content.length))
        ..add(_u16(name.length))
        ..add(_u16(0))
        ..add(name);
      await writeBytes(local.takeBytes());
      await writeBytes(content);
      central.add(
        _CentralEntry(
          name: name,
          crc: crc,
          size: content.length,
          offset: offset,
        ),
      );
    }

    final centralOffset = position;
    for (final entry in central) {
      final record = BytesBuilder(copy: false)
        ..add(_u32(0x02014b50))
        ..add(_u16(20))
        ..add(_u16(20))
        ..add(_u16(0x0800))
        ..add(_u16(0))
        ..add(_u16(0))
        ..add(_u16(0))
        ..add(_u32(entry.crc))
        ..add(_u32(entry.size))
        ..add(_u32(entry.size))
        ..add(_u16(entry.name.length))
        ..add(_u16(0))
        ..add(_u16(0))
        ..add(_u16(0))
        ..add(_u16(0))
        ..add(_u32(0))
        ..add(_u32(entry.offset))
        ..add(entry.name);
      await writeBytes(record.takeBytes());
    }
    final centralSize = position - centralOffset;
    final end = BytesBuilder(copy: false)
      ..add(_u32(0x06054b50))
      ..add(_u16(0))
      ..add(_u16(0))
      ..add(_u16(central.length))
      ..add(_u16(central.length))
      ..add(_u32(centralSize))
      ..add(_u32(centralOffset))
      ..add(_u16(0));
    await writeBytes(end.takeBytes());
  } finally {
    await output.close();
  }
  if (await destination.exists()) {
    await destination.delete();
  }
  return partial.rename(destination.path);
}

Uint8List _u16(int value) {
  final data = ByteData(2)..setUint16(0, value, Endian.little);
  return data.buffer.asUint8List();
}

Uint8List _u32(int value) {
  final data = ByteData(4)..setUint32(0, value, Endian.little);
  return data.buffer.asUint8List();
}

final List<int> _crcTable = List<int>.generate(256, (index) {
  var value = index;
  for (var bit = 0; bit < 8; bit++) {
    value = (value & 1) != 0 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  }
  return value;
});

int crc32(List<int> bytes) {
  var crc = 0xffffffff;
  for (final byte in bytes) {
    crc = _crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) & 0xffffffff;
}
