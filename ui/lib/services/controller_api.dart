import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/agent_models.dart';
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
    this.apiToken = AppConfig.apiToken,
    this.timeout = const Duration(seconds: 5),
  });

  final String baseUrl;
  final String apiToken;
  final Duration timeout;

  Uri endpoint(String path) {
    final normalized = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$baseUrl$normalized');
  }

  Uri get healthEndpoint => endpoint('/api/v1/health');
  Uri get tasksEndpoint => endpoint('/api/v1/tasks');
  Uri get eventsEndpoint => endpoint('/api/v1/events');
  Uri eventStreamEndpoint({required int afterSequence}) =>
      endpoint('/api/v1/events/stream').replace(
        queryParameters: {'after_sequence': afterSequence.toString()},
      );
  Uri get emergencyStopEndpoint => endpoint('/api/v1/safety/emergency-stop');
  Uri get emergencyStopEngageEndpoint =>
      endpoint('/api/v1/safety/emergency-stop/engage');
  Uri get emergencyStopResetEndpoint =>
      endpoint('/api/v1/safety/emergency-stop/reset');
  Uri get policiesEndpoint => endpoint('/api/v1/policies');
  Uri get pluginsEndpoint => endpoint('/api/v1/plugins');
  Uri get targetsEndpoint => endpoint('/api/v1/targets');
  Uri get edgeAgentsEndpoint => endpoint('/api/v1/edge-agents');
  Uri get agentsEndpoint => endpoint('/api/v1/agents');
  Uri get agentRuntimeEndpoint => endpoint('/api/v1/agents/runtime');
  Uri get agentDashboardEndpoint => endpoint('/api/v1/agent-dashboard');
  Uri get chatOrganizerEndpoint => endpoint('/api/v1/chat-organizer');
  Uri get organizedChatsEndpoint => endpoint(
        '/api/v1/chat-organizer/chats',
      ).replace(queryParameters: const {'limit': '500'});
  Uri get agentTasksEndpoint => endpoint('/api/v1/agent-tasks');
  Uri get processingRunsEndpoint => endpoint('/api/v1/processing/runs');
  Uri get modelProcessingRunsEndpoint =>
      endpoint('/api/v1/processing/model-runs');
  Uri get sandboxStartEndpoint =>
      endpoint('/api/v1/targets/windows-sandbox/start');

  Uri sandboxFrameEndpoint({required int cacheKey}) {
    return endpoint('/api/v1/targets/windows-sandbox/frame').replace(
      queryParameters: {'frame': cacheKey.toString()},
    );
  }

  Map<String, String> get _headers => {
        if (apiToken.isNotEmpty) 'X-BoxBrain-Token': apiToken,
      };

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

  Future<TaskSummary> createTask({
    required String goal,
    required String targetId,
    required String policyProfile,
  }) async {
    final json = await _postJson(
      tasksEndpoint,
      {
        'goal': goal,
        'target_id': targetId,
        'policy_profile': policyProfile,
      },
    );
    return TaskSummary.fromJson(json as Map<String, dynamic>);
  }

  Future<EmergencyStopState> fetchEmergencyStop() async {
    final json = await _getJson(emergencyStopEndpoint);
    return EmergencyStopState.fromJson(json as Map<String, dynamic>);
  }

  Future<EmergencyStopState> engageEmergencyStop({
    String reason = 'Operator activated emergency stop from dashboard.',
  }) async {
    final json = await _postJson(
      emergencyStopEngageEndpoint,
      {'reason': reason},
    );
    return EmergencyStopState.fromJson(json as Map<String, dynamic>);
  }

  Future<EmergencyStopState> resetEmergencyStop() async {
    final json = await _postJson(
      emergencyStopResetEndpoint,
      const {'confirmation': 'RESET'},
    );
    return EmergencyStopState.fromJson(json as Map<String, dynamic>);
  }

  Future<List<AuditEventSummary>> fetchEvents() async {
    final json = await _getJson(eventsEndpoint) as List<dynamic>;
    return json
        .map((item) => AuditEventSummary.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Stream<AuditEventSummary> streamEvents({int afterSequence = 0}) async* {
    final client = http.Client();
    try {
      final request = http.Request(
        'GET',
        eventStreamEndpoint(afterSequence: afterSequence),
      )..headers.addAll({
          ..._headers,
          'Accept': 'text/event-stream',
          if (afterSequence > 0) 'Last-Event-ID': afterSequence.toString(),
        });
      final response = await client.send(request).timeout(timeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final body = await response.stream.bytesToString();
        throw ControllerApiException(
          _errorMessage(
            http.Response(body, response.statusCode, headers: response.headers),
          ),
        );
      }

      String? data;
      await for (final line in response.stream
          .transform(utf8.decoder)
          .transform(const LineSplitter())) {
        if (line.isEmpty) {
          if (data != null) {
            try {
              final json = jsonDecode(data) as Map<String, dynamic>;
              yield AuditEventSummary.fromJson(json);
            } on FormatException {
              throw const ControllerApiException(
                'Controller returned an invalid audit event.',
              );
            }
          }
          data = null;
        } else if (line.startsWith('data:')) {
          final value = line.substring(5).trimLeft();
          data = data == null ? value : '$data\n$value';
        }
      }
    } on TimeoutException {
      throw const ControllerApiException('Controller stream timed out.');
    } on SocketException {
      throw const ControllerApiException('Controller is not reachable.');
    } on http.ClientException {
      throw const ControllerApiException('Controller stream failed.');
    } finally {
      client.close();
    }
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

  Future<List<TargetSummary>> fetchTargets() async {
    final json = await _getJson(targetsEndpoint) as List<dynamic>;
    return json
        .map((item) => TargetSummary.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<EdgeAgentSummary>> fetchEdgeAgents() async {
    final json = await _getJson(edgeAgentsEndpoint) as List<dynamic>;
    return json
        .map((item) => EdgeAgentSummary.fromJson(item as Map<String, dynamic>))
        .toList(growable: false);
  }

  Future<List<ProcessingAgentSummary>> fetchProcessingAgents() async {
    final json = await _getJson(agentsEndpoint) as List<dynamic>;
    return json
        .map(
          (item) => ProcessingAgentSummary.fromJson(
            item as Map<String, dynamic>,
          ),
        )
        .toList(growable: false);
  }

  Future<ModelRuntimeSummary> fetchModelRuntime() async {
    final json = await _getJson(agentRuntimeEndpoint);
    return ModelRuntimeSummary.fromJson(json as Map<String, dynamic>);
  }

  Future<AgentWorkspaceSummary> fetchAgentWorkspace() async {
    final json = await _getJson(agentDashboardEndpoint);
    return AgentWorkspaceSummary.fromJson(json as Map<String, dynamic>);
  }

  Future<ChatOrganizerSummary> fetchChatOrganizer() async {
    final json = await _getJson(chatOrganizerEndpoint);
    return ChatOrganizerSummary.fromJson(json as Map<String, dynamic>);
  }

  Future<List<OrganizedChatSummary>> fetchOrganizedChats() async {
    final json = await _getJson(organizedChatsEndpoint) as List<dynamic>;
    return json
        .map(
          (item) => OrganizedChatSummary.fromJson(
            item as Map<String, dynamic>,
          ),
        )
        .toList(growable: false);
  }

  Future<List<AgentTaskSummary>> fetchAgentTasks() async {
    final json = await _getJson(agentTasksEndpoint) as List<dynamic>;
    return json
        .map(
          (item) => AgentTaskSummary.fromJson(item as Map<String, dynamic>),
        )
        .toList(growable: false);
  }

  Future<ProcessingSubmissionResult> processAgentIntake({
    required String content,
    String source = 'voice',
    String? projectHint,
    int tokenBudget = 2000,
    bool useModel = false,
  }) async {
    final json = await _postJson(
      useModel ? modelProcessingRunsEndpoint : processingRunsEndpoint,
      {
        'content': content,
        'source': source,
        if (projectHint != null && projectHint.trim().isNotEmpty)
          'project_hint': projectHint.trim(),
        'token_budget': tokenBudget,
        'external_access_allowed': false,
      },
    ) as Map<String, dynamic>;
    return useModel
        ? ProcessingSubmissionResult.fromModelJson(json)
        : ProcessingSubmissionResult.fromLocalJson(json);
  }

  Future<String> startSandbox() async {
    final json = await _postJson(sandboxStartEndpoint, const {});
    return (json as Map<String, dynamic>)['status'] as String;
  }

  Future<Uint8List> fetchSandboxFrame({required int cacheKey}) async {
    final response = await _request(
      () => http.get(
        sandboxFrameEndpoint(cacheKey: cacheKey),
        headers: _headers,
      ),
    );
    if (response.headers['content-type']?.startsWith('image/png') != true) {
      throw const ControllerApiException(
        'Controller returned an invalid Sandbox frame.',
      );
    }
    return response.bodyBytes;
  }

  Future<dynamic> _getJson(Uri uri) async {
    return _requestJson(() => http.get(uri, headers: _headers));
  }

  Future<dynamic> _postJson(Uri uri, Map<String, dynamic> body) async {
    return _requestJson(
      () => http.post(
        uri,
        headers: {..._headers, 'Content-Type': 'application/json'},
        body: jsonEncode(body),
      ),
    );
  }

  Future<dynamic> _requestJson(
    Future<http.Response> Function() request,
  ) async {
    final response = await _request(request);
    try {
      return jsonDecode(response.body);
    } on FormatException {
      throw const ControllerApiException('Controller returned invalid data.');
    }
  }

  Future<http.Response> _request(
    Future<http.Response> Function() request,
  ) async {
    try {
      final response = await request().timeout(timeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final message = _errorMessage(response);
        throw ControllerApiException(message);
      }
      return response;
    } on TimeoutException {
      throw const ControllerApiException('Controller request timed out.');
    } on SocketException {
      throw const ControllerApiException('Controller is not reachable.');
    } on http.ClientException {
      throw const ControllerApiException('Controller connection failed.');
    }
  }

  String _errorMessage(http.Response response) {
    try {
      final json = jsonDecode(response.body);
      if (json case {'detail': final String detail}) return detail;
    } on FormatException {
      // Fall back to the status-only message below.
    }
    return 'Controller returned HTTP ${response.statusCode}.';
  }
}
