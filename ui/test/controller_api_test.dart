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
  test('chat import and task actions use authenticated controller routes',
      () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() => server.close(force: true));
    var requestCount = 0;

    server.listen((request) async {
      requestCount += 1;
      expect(request.method, 'POST');
      expect(request.headers.value('X-BoxBrain-Token'), 'test-token');
      final body = jsonDecode(await utf8.decoder.bind(request).join())
          as Map<String, dynamic>;
      request.response.headers.contentType = ContentType.json;

      if (request.uri.path == '/api/v1/chat-organizer/import') {
        expect(body['source'], 'chatgpt_app_index');
        expect(body['chats'], isEmpty);
        request.response.write(
          jsonEncode({
            'id': 'import-1',
            'source': 'chatgpt_app_index',
            'captured_at': '2026-07-28T14:00:00Z',
            'imported_at': '2026-07-28T14:00:01Z',
            'source_project_count': 0,
            'chat_count': 0,
            'created_count': 0,
            'updated_count': 0,
            'unchanged_count': 0,
            'unassigned_count': 0,
            'suggested_move_count': 0,
          }),
        );
      } else {
        expect(
          request.uri.path,
          '/api/v1/agent-tasks/agent-task-1/status',
        );
        expect(body['status'], 'done');
        request.response.write(
          jsonEncode({
            'id': 'agent-task-1',
            'project_key': 'boxbrain',
            'project': 'BoxBrain',
            'title': 'Finish the interface.',
            'status': 'done',
            'source_run_id': 'run-1',
            'created_at': '2026-07-28T14:00:00Z',
            'updated_at': '2026-07-28T14:00:01Z',
          }),
        );
      }
      await request.response.close();
    });

    final api = ControllerApi(
      baseUrl: 'http://127.0.0.1:${server.port}',
      apiToken: 'test-token',
    );
    final importResult = await api.importChatOrganizerSnapshot(
      '{"source":"chatgpt_app_index",'
      '"captured_at":"2026-07-28T14:00:00Z",'
      '"projects":[],"chats":[]}',
    );
    final task = await api.updateAgentTaskStatus(
      taskId: 'agent-task-1',
      status: 'done',
    );

    expect(requestCount, 2);
    expect(importResult.chatCount, 0);
    expect(task.status, 'done');
  });
}
