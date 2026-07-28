import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:boxbrain_ui/services/controller_api.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('authenticated audit stream resumes and parses SSE events', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    final requestSeen = Completer<void>();

    server.listen((request) async {
      expect(request.uri.path, '/api/v1/events/stream');
      expect(request.uri.queryParameters['after_sequence'], '7');
      expect(request.headers.value('Last-Event-ID'), '7');
      expect(request.headers.value('X-BoxBrain-Token'), 'test-token');
      requestSeen.complete();

      request.response.headers.contentType = ContentType(
        'text',
        'event-stream',
        charset: 'utf-8',
      );
      final event = {
        'sequence': 8,
        'id': 'event-8',
        'event_type': 'safety.emergency_stop_engaged',
        'task_id': null,
        'target_id': null,
        'message': 'Emergency stop engaged.',
        'details': {'result': 'engaged'},
        'created_at': '2026-07-24T12:00:00Z',
      };
      request.response.write(
        'id: 8\nevent: safety.emergency_stop_engaged\n'
        'data: ${jsonEncode(event)}\n\n',
      );
      await request.response.close();
    });

    final api = ControllerApi(
      baseUrl: 'http://127.0.0.1:${server.port}',
      apiToken: 'test-token',
    );
    final event = await api
        .streamEvents(afterSequence: 7)
        .first
        .timeout(const Duration(seconds: 3));

    await requestSeen.future;
    expect(event.sequence, 8);
    expect(event.eventType, 'safety.emergency_stop_engaged');
    expect(event.message, 'Emergency stop engaged.');
  });
  test('authenticated local agent intake posts the safe request shape',
      () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));

    server.listen((request) async {
      expect(request.method, 'POST');
      expect(request.uri.path, '/api/v1/processing/runs');
      expect(request.headers.value('X-BoxBrain-Token'), 'test-token');
      final body = jsonDecode(await utf8.decoder.bind(request).join())
          as Map<String, dynamic>;
      expect(body['content'], 'Build the agent workspace.');
      expect(body['source'], 'voice');
      expect(body['token_budget'], 2000);
      expect(body['external_access_allowed'], isFalse);

      request.response.headers.contentType = ContentType.json;
      request.response.write(
        jsonEncode({
          'id': 'run-1',
          'normalized_input': 'Build the agent workspace.',
          'project': 'BoxBrain',
          'intent': 'build',
          'status': 'completed',
          'steps': [
            {
              'agent_id': 'orchestrator',
              'status': 'completed',
              'summary': 'Normalized and routed the intake.',
            },
          ],
        }),
      );
      await request.response.close();
    });

    final api = ControllerApi(
      baseUrl: 'http://127.0.0.1:${server.port}',
      apiToken: 'test-token',
    );
    final result = await api.processAgentIntake(
      content: 'Build the agent workspace.',
    );

    expect(result.localRun.project, 'BoxBrain');
    expect(result.localRun.steps.single.agentId, 'orchestrator');
    expect(result.usedModel, isFalse);
  });
}
