import 'package:flutter/material.dart';

import 'screens/dashboard_screen.dart';
import 'services/controller_api.dart';

class BoxBrainApp extends StatelessWidget {
  const BoxBrainApp({this.controllerApi, super.key});

  final ControllerApi? controllerApi;

  @override
  Widget build(BuildContext context) {
    const seedColor = Color(0xFF6C63FF);
    final colorScheme = ColorScheme.fromSeed(
      seedColor: seedColor,
      brightness: Brightness.dark,
      surface: const Color(0xFF151821),
    );

    return MaterialApp(
      title: 'BoxBrain',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: colorScheme,
        scaffoldBackgroundColor: const Color(0xFF0C0F16),
        useMaterial3: true,
        cardTheme: const CardThemeData(
          color: Color(0xFF151821),
          elevation: 0,
          margin: EdgeInsets.zero,
        ),
        navigationRailTheme: const NavigationRailThemeData(
          backgroundColor: Color(0xFF11141C),
        ),
      ),
      home: DashboardScreen(api: controllerApi ?? const ControllerApi()),
    );
  }
}
