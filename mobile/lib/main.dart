import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  runApp(const AtelierApp());
}

class AtelierApp extends StatelessWidget {
  const AtelierApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Atelier Menuiserie',
      theme: ThemeData(
        primarySwatch: Colors.blue,
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}

// --- MODEL ---

class TimeLog {
  final int? id;
  final String orderRef;
  final String station;
  final String startTime;
  final String? endTime;
  final int synced; // 0: No, 1: Yes

  TimeLog({
    this.id,
    required this.orderRef,
    required this.station,
    required this.startTime,
    this.endTime,
    this.synced = 0,
  });

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'orderRef': orderRef,
      'station': station,
      'startTime': startTime,
      'endTime': endTime,
      'synced': synced,
    };
  }
}

// --- DATABASE ---

class DatabaseHelper {
  static final DatabaseHelper instance = DatabaseHelper._init();
  static Database? _database;

  DatabaseHelper._init();

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDB('atelier.db');
    return _database!;
  }

  Future<Database> _initDB(String filePath) async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, filePath);

    return await openDatabase(path, version: 1, onCreate: _createDB);
  }

  Future _createDB(Database db, int version) async {
    await db.execute('''
    CREATE TABLE logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      orderRef TEXT NOT NULL,
      station TEXT NOT NULL,
      startTime TEXT NOT NULL,
      endTime TEXT,
      synced INTEGER NOT NULL DEFAULT 0
    )
    ''');
  }

  Future<int> create(TimeLog log) async {
    final db = await instance.database;
    return await db.insert('logs', log.toMap());
  }

  Future<int> update(TimeLog log) async {
    final db = await instance.database;
    return await db.update(
      'logs',
      log.toMap(),
      where: 'id = ?',
      whereArgs: [log.id],
    );
  }
  
  Future<List<TimeLog>> getUnsyncedLogs() async {
    final db = await instance.database;
    final result = await db.query('logs', where: 'synced = ?', whereArgs: [0]);
    return result.map((json) => TimeLog(
      id: json['id'] as int,
      orderRef: json['orderRef'] as String,
      station: json['station'] as String,
      startTime: json['startTime'] as String,
      endTime: json['endTime'] as String?,
      synced: json['synced'] as int,
    )).toList();
  }
}

// --- SYNC SERVICE ---

class SyncService {
  static Future<void> syncLogs() async {
    final prefs = await SharedPreferences.getInstance();
    final apiUrl = prefs.getString('api_url') ?? 'http://10.0.2.2:8000'; // Emulator localhost

    final unsynced = await DatabaseHelper.instance.getUnsyncedLogs();
    
    for (var log in unsynced) {
      if (log.endTime == null) continue; // Only sync completed logs? Or start logs too?
      // V1 Backend expects "add_time_log" with duration or end time.
      // Let's assume we send when stopped.
      
      try {
        final start = DateTime.parse(log.startTime);
        final end = DateTime.parse(log.endTime!);
        final duration = end.difference(start).inSeconds;

        final response = await http.post(
          Uri.parse('$apiUrl/orders/${log.orderRef}/log'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({
            'station': log.station,
            'start_time': log.startTime,
            'end_time': log.endTime,
            'duration_seconds': duration
          }),
        );

        if (response.statusCode == 200) {
          await DatabaseHelper.instance.update(
            TimeLog(
              id: log.id, 
              orderRef: log.orderRef, 
              station: log.station, 
              startTime: log.startTime, 
              endTime: log.endTime, 
              synced: 1
            )
          );
          print("Synced log ${log.id}");
        } else {
             print("Failed to sync log ${log.id}: ${response.body}");
        }
      } catch (e) {
        print("Sync error: $e");
      }
    }
  }
}

// --- UI ---

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final TextEditingController _urlController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _loadConfig();
  }

  _loadConfig() async {
    final prefs = await SharedPreferences.getInstance();
    _urlController.text = prefs.getString('api_url') ?? 'http://10.0.2.2:8000';
  }

  _saveConfig() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('api_url', _urlController.text);
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Config Saved')));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Atelier Menuiserie V1')),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            ElevatedButton.icon(
              icon: const Icon(Icons.qr_code_scanner, size: 40),
              label: const Text("SCANNER ORDRE", style: TextStyle(fontSize: 20)),
              style: ElevatedButton.styleFrom(padding: const EdgeInsets.all(20)),
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (context) => const ScanScreen()),
                );
              },
            ),
            const SizedBox(height: 40),
            ElevatedButton.icon(
              icon: const Icon(Icons.sync, size: 30),
              label: const Text("SYNCHRONISER"),
              onPressed: () async {
                await SyncService.syncLogs();
                ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Sync Done')));
              },
            ),
             const SizedBox(height: 40),
             Padding(
               padding: const EdgeInsets.all(20.0),
               child: TextField(
                 controller: _urlController,
                 decoration: const InputDecoration(labelText: 'API URL', border: OutlineInputBorder()),
               ),
             ),
             TextButton(onPressed: _saveConfig, child: const Text("Save Config"))
          ],
        ),
      ),
    );
  }
}

class ScanScreen extends StatelessWidget {
  const ScanScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Scan QR")),
      body: MobileScanner(
        onDetect: (capture) {
          final List<Barcode> barcodes = capture.barcodes;
          for (final barcode in barcodes) {
            final String? code = barcode.rawValue;
            if (code != null) {
              // Expected: CMD-XXXX|LxH|MAT
              Navigator.pop(context);
              Navigator.push(
                context, 
                MaterialPageRoute(builder: (context) => WorkScreen(qrCode: code))
              );
              break; 
            }
          }
        },
      ),
    );
  }
}

class WorkScreen extends StatefulWidget {
  final String qrCode;
  const WorkScreen({super.key, required this.qrCode});

  @override
  State<WorkScreen> createState() => _WorkScreenState();
}

class _WorkScreenState extends State<WorkScreen> {
  String orderRef = "";
  String material = "";
  String dimensions = "";
  
  bool isWorking = false;
  DateTime? startTime;
  TimeLog? currentLog;
  
  // Hardcoded stations for V1 MVP - In real app, select from list or config
  String selectedStation = "PVC_DEBIT"; 
  final List<String> pvcStations = [
    "PVC_DEBIT", "PVC_SOUDURE", "PVC_ASSEMBLAGE", "PVC_VITRAGE", "PVC_CONTROLE"
  ];
  final List<String> aluStations = [
    "ALU_DEBIT", "ALU_USINAGE", "ALU_ASSEMBLAGE", "ALU_VITRAGE", "ALU_CONTROLE"
  ];

  @override
  void initState() {
    super.initState();
    _parseQR();
  }

  void _parseQR() {
    // CMD-XXXX|LxH|MAT
    try {
      final parts = widget.qrCode.split('|');
      if (parts.length >= 3) {
        orderRef = parts[0];
        dimensions = parts[1];
        material = parts[2];
        
        // Auto-select list based on material
        if (material == "ALU") {
            selectedStation = aluStations[0];
        } else {
            selectedStation = pvcStations[0];
        }
      } else {
        orderRef = "INVALID QR";
      }
    } catch (e) {
      orderRef = "ERROR";
    }
  }

  void _startWork() async {
    setState(() {
      isWorking = true;
      startTime = DateTime.now();
    });
    
    // Create Log Entry
    final log = TimeLog(
      orderRef: orderRef,
      station: selectedStation,
      startTime: startTime!.toIso8601String(),
    );
    
    final id = await DatabaseHelper.instance.create(log);
    // Reload to get ID
    currentLog = TimeLog(
        id: id,
        orderRef: log.orderRef,
        station: log.station,
        startTime: log.startTime
    );
  }

  void _stopWork() async {
    if (currentLog == null) return;
    
    final endTime = DateTime.now();
    final updatedLog = TimeLog(
      id: currentLog!.id,
      orderRef: currentLog!.orderRef,
      station: currentLog!.station,
      startTime: currentLog!.startTime,
      endTime: endTime.toIso8601String(),
      synced: 0
    );
    
    await DatabaseHelper.instance.update(updatedLog);
    
    setState(() {
      isWorking = false;
      startTime = null;
      currentLog = null;
    });
    
    // Auto sync
    SyncService.syncLogs();
    
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Travail terminé & enregistré')));
      Navigator.pop(context); // Go back to Home/Scan
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text("Ordre: $orderRef")),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text("Dimensions: $dimensions", style: const TextStyle(fontSize: 18)),
            Text("Matière: $material", style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            const Divider(),
            const Text("Poste de travail:", style: TextStyle(fontSize: 16)),
            DropdownButton<String>(
              value: selectedStation,
              isExpanded: true,
              items: (material == "ALU" ? aluStations : pvcStations).map((String value) {
                return DropdownMenuItem<String>(
                  value: value,
                  child: Text(value),
                );
              }).toList(),
              onChanged: isWorking ? null : (newValue) { // Disable change while working
                setState(() {
                  selectedStation = newValue!;
                });
              },
            ),
            const Spacer(),
            if (!isWorking)
              ElevatedButton(
                onPressed: _startWork,
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.green,
                  padding: const EdgeInsets.symmetric(vertical: 30),
                ),
                child: const Text("START", style: TextStyle(fontSize: 30, color: Colors.white)),
              )
            else
              Column(
                children: [
                   Text("En cours depuis: ${startTime != null ? DateFormat('HH:mm:ss').format(startTime!) : ''}", 
                        style: const TextStyle(fontSize: 20, color: Colors.green)),
                   const SizedBox(height: 20),
                   Row(
                     children: [
                       Expanded(
                         child: ElevatedButton(
                           onPressed: () { /* Pause Logic V3? */ }, 
                           style: ElevatedButton.styleFrom(backgroundColor: Colors.orange, padding: const EdgeInsets.symmetric(vertical: 20)),
                           child: const Text("PAUSE", style: TextStyle(fontSize: 20, color: Colors.white)),
                         ),
                       ),
                       const SizedBox(width: 20),
                       Expanded(
                         child: ElevatedButton(
                           onPressed: _stopWork,
                           style: ElevatedButton.styleFrom(backgroundColor: Colors.red, padding: const EdgeInsets.symmetric(vertical: 20)),
                           child: const Text("STOP", style: TextStyle(fontSize: 20, color: Colors.white)),
                         ),
                       ),
                     ],
                   )
                ],
              ),
            const Spacer(),
          ],
        ),
      ),
    );
  }
}
