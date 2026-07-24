import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/controller_status.dart';

class ControllerApiException implements Exception {
  const ControllerApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class ControllerApi {
  const ControllerApi({
    this.baseUrl = AppConfig.controllerBaseUrl,
    this.timeout = const Duration(seconds: 5),
  });

  final String baseUrl;
  final Duration timeout;

  Uri endpoint(String path) {
    final normalized = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$baseUrl$normalized');
  }

  Uri get healthEndpoint => endpoint('/api/v1/health');
  Uri get tasksEndpoint => endpoint('/api/v1/tasks');
  Uri get policiesEndpoint => endpoint('/api/v1/policies');
  Uri get pluginsEndpoint => endpoint('/api/v1/plugins');

  Future<ControllerHealth> fetchHealth() async {
    final json = await _getJson(healthEndpoint);
    return ControllerHealth.fromJson(json as Map<String, dynamic>);
  }

  Future<List<TaskSummary>> fetchTasks() async {
    final json = await _getJson(tasksEndpoint) as List<dynamic>;
    return json
        .map((item) => TaskSummary.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<PolicySummary>> fetchPolicies() async {
    final json = await _getJson(policiesEndpoint) as List<dynamic>;
    return json
        .map((item) => PolicySummary.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<PluginSummary>> fetchPlugins() async {
    final json = await _getJson(pluginsEndpoint) as List<dynamic>;
    return json
        .map((item) => PluginSummary.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<dynamic> _getJson(Uri uri) async {
    try {
      final response = await http.get(uri).timeout(timeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw ControllerApiException(
          'Controller returned HTTP ${response.statusCode}.',
        );
      }
      return jsonDecode(response.body);
    } on TimeoutException {
      throw const ControllerApiException('Controller request timed out.');
    } on SocketException {
      throw const ControllerApiException('Controller is not reachable.');
    } on FormatException {
      throw const ControllerApiException('Controller returned invalid data.');
    } on http.ClientException {
      throw const ControllerApiException('Controller connection failed.');
    }
  }
}
