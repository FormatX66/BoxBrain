import 'dart:async';
import 'dart:typed_data';

import 'package:boxbrain_ui/app.dart';
import 'package:boxbrain_ui/models/controller_status.dart';
import 'package:boxbrain_ui/services/controller_api.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows live controller data and resource views', (tester) async {
    await tester.pumpWidget(
      const BoxBrainApp(controllerApi: _OnlineControllerApi()),
    );
    await tester.pumpAndSettle();

    expect(find.text('BoxBrain'), findsOneWidget);
    expect(find.text('Mission control'), findsOneWidget);
    expect(find.text('Online'), findsWidgets);
    expect(find.text('0.1.0'), findsOneWidget);
    expect(find.text('Token required'), findsOneWidget);
    expect(find.text('Live stream'), findsOneWidget);
    expect(find.text('Kali Pi edge agent'), findsOneWidget);
    expect(find.text('Connected through local SSH tunnel'), findsOneWidget);
    expect(find.text('1'), findsWidgets);

    await tester.tap(find.text('Policies'));
    await tester.pumpAndSettle();

    expect(find.text('3 profiles from the controller'), findsOneWidget);
    expect(find.text('Research'), findsOneWidget);
    expect(find.text('Open'), findsOneWidget);

    await tester.tap(find.text('Plugins'));
    await tester.pumpAndSettle();

    expect(find.text('Windows Sandbox Observer'), findsOneWidget);
    expect(find.textContaining('Out of process'), findsOneWidget);
    expect(find.textContaining('observation.frame'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.desktop_windows_outlined));
    await tester.pumpAndSettle();

    expect(find.text('Windows Sandbox is not running'), findsOneWidget);
    expect(find.text('Read-only access only'), findsOneWidget);
    expect(find.text('Open Windows Sandbox'), findsOneWidget);
    expect(find.text('Zero frame retention'), findsOneWidget);
    expect(
        find.textContaining('No frames are written to disk'), findsOneWidget);
    expect(find.textContaining('1280 px max'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.receipt_long_outlined));
    await tester.pumpAndSettle();

    expect(find.text('Audit log'), findsOneWidget);
    expect(
        find.text('Task queued; executor remains disabled.'), findsOneWidget);
    expect(find.text('1 append-only controller events'), findsOneWidget);
  });

  testWidgets('opens the fixed Sandbox profile from the Target screen', (
    tester,
  ) async {
    final api = _LaunchControllerApi();
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.desktop_windows_outlined));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Open Windows Sandbox'));
    await tester.pump();

    expect(api.startCalls, 1);
    expect(find.text('Opening Sandbox'), findsOneWidget);

    await tester.pump(const Duration(seconds: 2));
    await tester.pumpAndSettle();
  });

  testWidgets('queues an audited task for a connected target', (tester) async {
    final api = _QueueControllerApi();
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.task_alt_outlined));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Queue task'));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byType(TextFormField).first,
      'Observe the calculator window',
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Queue task').last);
    await tester.pumpAndSettle();

    expect(api.tasks, hasLength(1));
    expect(find.text('Observe the calculator window'), findsOneWidget);
    expect(find.text('Queued'), findsOneWidget);
  });

  testWidgets('engages and explicitly resets the emergency stop', (
    tester,
  ) async {
    final api = _SafetyControllerApi();
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Emergency stop'));
    await tester.pumpAndSettle();
    expect(find.text('Engage emergency stop?'), findsOneWidget);

    await tester.tap(find.text('Stop actions'));
    await tester.pumpAndSettle();
    expect(api.state.engaged, isTrue);
    expect(find.text('Emergency stop engaged'), findsOneWidget);

    await tester.tap(find.byTooltip('Reset emergency stop'));
    await tester.pumpAndSettle();
    expect(find.text('Reset emergency stop'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'RESET');
    await tester.pump();
    await tester.tap(find.text('Reset stop'));
    await tester.pumpAndSettle();

    expect(api.state.engaged, isFalse);
    expect(find.text('Emergency stop engaged'), findsNothing);
  });

  testWidgets('shows streamed audit events without a manual refresh', (
    tester,
  ) async {
    final api = _StreamingControllerApi();
    addTearDown(api.dispose);
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();
    for (var attempt = 0; attempt < 10 && !api.hasListener; attempt++) {
      await tester.pump(const Duration(milliseconds: 10));
    }
    expect(api.hasListener, isTrue);

    await tester.tap(find.byIcon(Icons.receipt_long_outlined));
    await tester.pumpAndSettle();
    expect(find.text('Emergency stop engaged by stream.'), findsNothing);

    api.emit(
      AuditEventSummary(
        sequence: 2,
        id: 'event-2',
        eventType: 'safety.emergency_stop_engaged',
        taskId: null,
        targetId: null,
        message: 'Emergency stop engaged by stream.',
        details: const {'result': 'engaged'},
        createdAt: DateTime.utc(2026, 7, 24, 12, 1),
      ),
    );
    await tester.pump();

    expect(find.text('Emergency stop engaged by stream.'), findsOneWidget);
    expect(find.text('2 append-only controller events'), findsOneWidget);
  });

  testWidgets('shows retryable offline state when controller fails', (
    tester,
  ) async {
    await tester.pumpWidget(
      const BoxBrainApp(controllerApi: _OfflineControllerApi()),
    );
    await tester.pumpAndSettle();

    expect(find.text('Offline'), findsWidgets);
    expect(find.text('Controller is not reachable.'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });
}

class _OnlineControllerApi extends ControllerApi {
  const _OnlineControllerApi({this.targetConnected = false});

  final bool targetConnected;

  @override
  Future<EmergencyStopState> fetchEmergencyStop() async => EmergencyStopState(
        engaged: false,
        reason: null,
        generation: 0,
        changedAt: DateTime.utc(2026, 7, 24, 12),
      );

  @override
  Future<ControllerHealth> fetchHealth() async => const ControllerHealth(
        service: 'boxbrain-controller',
        version: '0.1.0',
        status: 'ok',
        environment: 'development',
        executorEnabled: false,
        authenticationRequired: true,
        eventStreamEnabled: true,
      );

  @override
  Future<Uint8List> fetchSandboxFrame({required int cacheKey}) async {
    throw const ControllerApiException('Test frame unavailable.');
  }

  @override
  Stream<AuditEventSummary> streamEvents({int afterSequence = 0}) =>
      const Stream.empty();

  @override
  Future<List<TaskSummary>> fetchTasks() async => const [];

  @override
  Future<List<AuditEventSummary>> fetchEvents() async => [
        AuditEventSummary(
          sequence: 1,
          id: 'event-1',
          eventType: 'task.queued',
          taskId: 'task-1',
          targetId: 'windows-sandbox',
          message: 'Task queued; executor remains disabled.',
          details: const {'status': 'queued'},
          createdAt: DateTime.utc(2026, 7, 24, 12),
        ),
      ];

  @override
  Future<List<PolicySummary>> fetchPolicies() async => const [
        PolicySummary(
          name: 'safe',
          description: 'Confirm consequential actions.',
          confirmationsRequired: true,
          immutableAuditLog: true,
          isolatedTargetRequired: true,
          emergencyStopRequired: true,
        ),
        PolicySummary(
          name: 'research',
          description: 'Reduced confirmations in an isolated target.',
          confirmationsRequired: false,
          immutableAuditLog: true,
          isolatedTargetRequired: true,
          emergencyStopRequired: true,
        ),
        PolicySummary(
          name: 'open',
          description: 'Experimental disposable-lab profile.',
          confirmationsRequired: false,
          immutableAuditLog: true,
          isolatedTargetRequired: true,
          emergencyStopRequired: true,
        ),
      ];

  @override
  Future<List<PluginSummary>> fetchPlugins() async => const [
        PluginSummary(
          id: 'boxbrain.windows-sandbox-observer',
          name: 'Windows Sandbox Observer',
          version: '0.1.0',
          description: 'Read-only observer plugin.',
          enabled: true,
          protocolVersion: '1',
          capabilities: ['observation.describe', 'observation.frame'],
          processBoundary: 'out-of-process',
          targetId: 'windows-sandbox',
        ),
      ];

  @override
  Future<List<EdgeAgentSummary>> fetchEdgeAgents() async => const [
        EdgeAgentSummary(
          id: 'kali-pi',
          name: 'Kali Pi Edge Agent',
          role: 'edge-agent',
          transport: 'ssh-tunnel',
          mode: 'read-only-advisory',
          connected: true,
          version: '0.6.0',
          hostname: 'kali-pi',
          targetCount: 1,
          recommendationCount: 2,
        ),
      ];

  @override
  Future<List<TargetSummary>> fetchTargets() async => [
        TargetSummary(
          id: 'windows-sandbox',
          name: 'Windows Sandbox',
          transport: 'out-of-process-plugin',
          mode: 'read-only',
          connected: targetConnected,
          windowTitle: 'Windows Sandbox',
          frameEndpoint:
              targetConnected ? '/api/v1/targets/windows-sandbox/frame' : null,
          inputEnabled: false,
          observerPluginId: 'boxbrain.windows-sandbox-observer',
          observerProcessBoundary: 'out-of-process',
          observationStatus: 'ready',
          observationPolicy: const ObservationPolicySummary(
            maxFrameWidth: 1280,
            maxFrameBytes: 8 * 1024 * 1024,
            redactionRegionCount: 0,
            evidenceRetention: 'none',
            maxRetainedFrames: 0,
            retentionMaxAgeSeconds: 0,
          ),
          startEnabled: true,
          startEndpoint: '/api/v1/targets/windows-sandbox/start',
        ),
      ];
}

class _LaunchControllerApi extends _OnlineControllerApi {
  _LaunchControllerApi();

  int startCalls = 0;

  @override
  Future<String> startSandbox() async {
    startCalls += 1;
    return 'starting';
  }
}

class _StreamingControllerApi extends _OnlineControllerApi {
  _StreamingControllerApi();

  final _controller = StreamController<AuditEventSummary>.broadcast(sync: true);

  bool get hasListener => _controller.hasListener;

  @override
  Stream<AuditEventSummary> streamEvents({int afterSequence = 0}) =>
      _controller.stream;

  void emit(AuditEventSummary event) => _controller.add(event);

  Future<void> dispose() => _controller.close();
}

class _SafetyControllerApi extends _OnlineControllerApi {
  _SafetyControllerApi();

  EmergencyStopState state = EmergencyStopState(
    engaged: false,
    reason: null,
    generation: 0,
    changedAt: DateTime.utc(2026, 7, 24, 12),
  );

  @override
  Future<EmergencyStopState> fetchEmergencyStop() async => state;

  @override
  Future<EmergencyStopState> engageEmergencyStop({
    String reason = 'Operator activated emergency stop from dashboard.',
  }) async {
    state = EmergencyStopState(
      engaged: true,
      reason: reason,
      generation: state.generation + 1,
      changedAt: DateTime.utc(2026, 7, 24, 12, 1),
    );
    return state;
  }

  @override
  Future<EmergencyStopState> resetEmergencyStop() async {
    state = EmergencyStopState(
      engaged: false,
      reason: null,
      generation: state.generation + 1,
      changedAt: DateTime.utc(2026, 7, 24, 12, 2),
    );
    return state;
  }
}

class _QueueControllerApi extends _OnlineControllerApi {
  _QueueControllerApi() : super(targetConnected: true);

  final List<TaskSummary> tasks = [];

  @override
  Future<List<TaskSummary>> fetchTasks() async => List.unmodifiable(tasks);

  @override
  Future<TaskSummary> createTask({
    required String goal,
    required String targetId,
    required String policyProfile,
  }) async {
    final task = TaskSummary(
      id: 'task-1',
      goal: goal,
      targetId: targetId,
      policyProfile: policyProfile,
      status: 'queued',
      createdAt: DateTime.utc(2026, 7, 24, 12),
    );
    tasks.add(task);
    return task;
  }
}

class _OfflineControllerApi extends ControllerApi {
  const _OfflineControllerApi();

  @override
  Future<EmergencyStopState> fetchEmergencyStop() async =>
      const EmergencyStopState.unknown();

  @override
  Stream<AuditEventSummary> streamEvents({int afterSequence = 0}) =>
      const Stream.empty();

  @override
  Future<ControllerHealth> fetchHealth() async {
    throw const ControllerApiException('Controller is not reachable.');
  }

  @override
  Future<List<TaskSummary>> fetchTasks() async => const [];

  @override
  Future<List<AuditEventSummary>> fetchEvents() async => const [];

  @override
  Future<List<PolicySummary>> fetchPolicies() async => const [];

  @override
  Future<List<PluginSummary>> fetchPlugins() async => const [];

  @override
  Future<List<EdgeAgentSummary>> fetchEdgeAgents() async => const [];

  @override
  Future<List<TargetSummary>> fetchTargets() async => const [];
}
