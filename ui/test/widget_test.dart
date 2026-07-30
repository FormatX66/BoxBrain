import 'dart:async';
import 'dart:typed_data';

import 'package:boxbrain_ui/app.dart';
import 'package:boxbrain_ui/models/agent_models.dart';
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
    expect(find.text('wlan0'), findsOneWidget);
    expect(find.text('Blocked'), findsOneWidget);
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
    expect(find.text('Task queued; autonomous execution remains disabled.'),
        findsOneWidget);
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

  testWidgets('runs the local processing crew from the Agents workspace', (
    tester,
  ) async {
    final api = _AgentControllerApi();
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.smart_toy_outlined));
    await tester.pumpAndSettle();

    expect(find.text('Processing agents'), findsOneWidget);
    expect(find.text('The Conductor'), findsOneWidget);
    expect(find.text('Ready'), findsOneWidget);
    expect(find.text('ChatGPT organizer'), findsOneWidget);
    expect(find.text('3 chats'), findsOneWidget);
    expect(find.text('File structure'), findsOneWidget);
    expect(find.text('10 BoxBrain & Automation'), findsOneWidget);

    final boxBrainFolder = find.byKey(
      const Key('chat-folder-10 BoxBrain & Automation'),
    );
    await tester.ensureVisible(boxBrainFolder);
    await tester.pumpAndSettle();
    await tester.tap(boxBrainFolder);
    await tester.pumpAndSettle();
    expect(find.text('BoxBrain Repo Access'), findsOneWidget);
    expect(find.text('Ready to file'), findsOneWidget);

    await tester.enterText(
      find.byKey(const Key('agent-intake')),
      'Build the BoxBrain memory dashboard.',
    );
    await tester.ensureVisible(find.byKey(const Key('run-agent-crew')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('run-agent-crew')));
    await tester.pumpAndSettle();

    expect(api.processCalls, 1);
    expect(api.lastContent, 'Build the BoxBrain memory dashboard.');
    expect(api.lastUsedModel, isFalse);
    expect(find.text('Latest result'), findsOneWidget);
    expect(find.text('Build the BoxBrain memory dashboard.'), findsWidgets);
  });

  testWidgets('imports a ChatGPT organizer snapshot from the interface', (
    tester,
  ) async {
    final api = _AgentControllerApi();
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.smart_toy_outlined));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('import-chat-snapshot')));
    await tester.tap(find.byKey(const Key('import-chat-snapshot')));
    await tester.pump();

    await tester.enterText(
      find.byKey(const Key('chat-import-json')),
      '{"source":"chatgpt_app_index",'
      '"captured_at":"2026-07-28T14:00:00Z",'
      '"projects":[],"chats":[]}',
    );
    await tester.tap(find.byKey(const Key('confirm-chat-import')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(api.importCalls, 1);
    expect(api.lastSnapshot, contains('chatgpt_app_index'));
    expect(find.textContaining('Indexed 1 chats'), findsOneWidget);
  });

  testWidgets('updates a durable agent task from its action menu', (
    tester,
  ) async {
    final api = _AgentControllerApi();
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.smart_toy_outlined));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('agent-intake')),
      'Create a durable task.',
    );
    await tester.ensureVisible(find.byKey(const Key('run-agent-crew')));
    await tester.tap(find.byKey(const Key('run-agent-crew')));
    await tester.pumpAndSettle();

    final actions = find.byKey(const Key('agent-task-actions-agent-task-1'));
    await tester.ensureVisible(actions);
    await tester.tap(actions);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mark done'));
    await tester.pumpAndSettle();

    expect(api.taskUpdateCalls, 1);
    expect(api.agentTaskStatus, 'done');
    expect(find.text('Done'), findsWidgets);
    expect(find.text('Task marked Done.'), findsOneWidget);
  });
  testWidgets('tests and opens the built-in USB-C target', (tester) async {
    await tester.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _RemoteControllerApi();
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.desktop_windows_outlined));
    await tester.pumpAndSettle();
    expect(find.text('Connected hosts'), findsOneWidget);
    expect(find.text('Kali Pi USB-C'), findsOneWidget);

    final probe = find.byKey(const Key('probe-remote-remote-usb'));
    await tester.ensureVisible(probe);
    await tester.tap(probe);
    await tester.pumpAndSettle();
    expect(api.probeCalls, 1);

    final open = find.byKey(const Key('open-remote-remote-usb'));
    await tester.ensureVisible(open);
    await tester.tap(open);
    await tester.pump();
    await tester.enterText(
      find.byKey(const Key('remote-open-confirmation')),
      'OPEN',
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('confirm-open-remote')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(api.openCalls, 1);
    expect(find.textContaining('operator-controlled SSH'), findsOneWidget);
  });

  testWidgets('reviews and approves an AI Pi diagnostic', (tester) async {
    await tester.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _RemoteControllerApi();
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.desktop_windows_outlined));
    await tester.pumpAndSettle();
    final diagnose = find.byKey(const Key('diagnose-remote-remote-usb'));
    await tester.ensureVisible(diagnose);
    await tester.tap(diagnose);
    await tester.pump();

    expect(find.text('Proposal first, execution second'), findsOneWidget);
    await tester.enterText(
      find.byKey(const Key('diagnostic-goal')),
      'Check Pi disk space',
    );
    await tester.tap(find.byKey(const Key('propose-diagnostic')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(api.proposeCalls, 1);
    expect(api.lastDiagnosticGoal, 'Check Pi disk space');
    expect(find.text('Collect fixed read-only disk evidence.'), findsOneWidget);
    expect(find.text('disk usage'), findsOneWidget);

    await tester.enterText(
      find.byKey(const Key('diagnostic-run-confirmation')),
      'RUN',
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('execute-diagnostic')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(api.executeCalls, 1);
    expect(find.textContaining('/dev/root'), findsOneWidget);
    expect(find.byKey(const Key('diagnostic-output')), findsOneWidget);
  });

  testWidgets('adds an authorized SSH target from the Target screen', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final api = _RemoteControllerApi();
    await tester.pumpWidget(BoxBrainApp(controllerApi: api));
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.desktop_windows_outlined));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('add-remote-target')));
    await tester.tap(find.byKey(const Key('add-remote-target')));
    await tester.pump();

    await tester.enterText(
      find.byKey(const Key('remote-name')),
      'Repair PC',
    );
    await tester.enterText(
      find.byKey(const Key('remote-host')),
      '192.168.50.23',
    );
    await tester.enterText(
      find.byKey(const Key('remote-username')),
      'technician',
    );
    await tester.tap(find.byKey(const Key('remote-authorized')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('confirm-add-remote')));
    await tester.pumpAndSettle();

    expect(api.createCalls, 1);
    expect(find.text('Repair PC'), findsOneWidget);
    expect(find.text('192.168.50.23:22'), findsOneWidget);
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
          message: 'Task queued; autonomous execution remains disabled.',
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
  Future<List<RemoteTargetSummary>> fetchRemoteTargets() async => [
        RemoteTargetSummary(
          id: 'remote-usb',
          name: 'Kali Pi USB-C',
          transport: 'usb-c',
          host: '10.12.194.1',
          port: 22,
          username: 'kali',
          authorized: true,
          builtIn: true,
          status: 'online',
          credentialMode: 'dedicated-key',
          capabilities: const [
            'tcp-probe',
            'interactive-shell',
            'edge-diagnostics',
          ],
          lastCheckedAt: DateTime.utc(2026, 7, 28, 15),
          createdAt: DateTime.utc(2026, 7, 24, 12),
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
          version: '0.7.2',
          hostname: 'kali-pi',
          targetCount: 1,
          recommendationCount: 2,
          networkInterface: 'wlan0',
          wifiCredentialAudit: 'blocked',
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

class _AgentControllerApi extends _OnlineControllerApi {
  _AgentControllerApi();

  int processCalls = 0;
  int importCalls = 0;
  int taskUpdateCalls = 0;
  String? lastContent;
  String? lastSnapshot;
  bool? lastUsedModel;
  String agentTaskStatus = 'open';

  @override
  Future<List<ProcessingAgentSummary>> fetchProcessingAgents() async => const [
        ProcessingAgentSummary(
          id: 'orchestrator',
          name: 'Orchestrator',
          character: 'The Conductor',
          responsibility: 'Normalize intake and route the run.',
          capabilities: ['intake', 'routing'],
          executionMode: 'local-rule',
          enabled: true,
        ),
      ];

  @override
  Future<ModelRuntimeSummary> fetchModelRuntime() async =>
      const ModelRuntimeSummary(
        enabled: true,
        configured: true,
        sdkAvailable: true,
        ready: true,
        model: 'gpt-5.6-sol',
        executionMode: 'openai-agents-sdk',
        externalSideEffectsEnabled: false,
      );

  @override
  Future<AgentWorkspaceSummary> fetchAgentWorkspace() async =>
      AgentWorkspaceSummary(
        projectCount: processCalls == 0 ? 0 : 1,
        memoryCount: processCalls == 0 ? 0 : 1,
        openTaskCount: processCalls == 0 ? 0 : 1,
        completedTaskCount: 0,
        processingRunCount: processCalls,
        estimatedTokens: 80 * processCalls,
        providerTokensUsed: 0,
      );

  @override
  Future<ChatOrganizerSummary> fetchChatOrganizer() async =>
      ChatOrganizerSummary(
        totalChatCount: 3,
        sourceProjectCount: 1,
        unassignedCount: 2,
        suggestedMoveCount: 2,
        pinnedCount: 1,
        lastSyncAt: DateTime.utc(2026, 7, 28, 14),
        buckets: const [
          ChatProjectBucketSummary(
            name: '10 BoxBrain & Automation',
            chatCount: 2,
            isExistingChatGptProject: false,
          ),
          ChatProjectBucketSummary(
            name: 'Wet Beard website',
            chatCount: 1,
            isExistingChatGptProject: true,
          ),
        ],
        recentChats: [
          OrganizedChatSummary(
            externalId: 'chat-1',
            title: 'BoxBrain Repo Access',
            currentProject: null,
            suggestedProject: '10 BoxBrain & Automation',
            classificationReason: 'Matched BoxBrain.',
            confidence: 'medium',
            pinnedIndex: 1,
            updatedAt: DateTime.utc(2026, 7, 28, 13),
          ),
        ],
      );

  @override
  Future<List<OrganizedChatSummary>> fetchOrganizedChats() async => [
        OrganizedChatSummary(
          externalId: 'chat-1',
          title: 'BoxBrain Repo Access',
          currentProject: null,
          suggestedProject: '10 BoxBrain & Automation',
          classificationReason: 'Matched BoxBrain.',
          confidence: 'medium',
          pinnedIndex: 1,
          updatedAt: DateTime.utc(2026, 7, 28, 13),
        ),
      ];

  @override
  Future<List<AgentTaskSummary>> fetchAgentTasks() async => processCalls == 0
      ? const []
      : [
          AgentTaskSummary(
            id: 'agent-task-1',
            project: 'BoxBrain',
            title: 'Build the BoxBrain memory dashboard.',
            status: agentTaskStatus,
            createdAt: DateTime.utc(2026, 7, 27, 12),
            updatedAt: DateTime.utc(2026, 7, 27, 12),
          ),
        ];

  @override
  Future<ChatOrganizerImportSummary> importChatOrganizerSnapshot(
    String snapshot,
  ) async {
    importCalls += 1;
    lastSnapshot = snapshot;
    return const ChatOrganizerImportSummary(
      id: 'import-1',
      chatCount: 1,
      createdCount: 1,
      updatedCount: 0,
      unchangedCount: 0,
      suggestedMoveCount: 1,
    );
  }

  @override
  Future<AgentTaskSummary> updateAgentTaskStatus({
    required String taskId,
    required String status,
  }) async {
    taskUpdateCalls += 1;
    agentTaskStatus = status;
    return AgentTaskSummary(
      id: taskId,
      project: 'BoxBrain',
      title: 'Build the BoxBrain memory dashboard.',
      status: status,
      createdAt: DateTime.utc(2026, 7, 27, 12),
      updatedAt: DateTime.utc(2026, 7, 28, 12),
    );
  }

  @override
  Future<ProcessingSubmissionResult> processAgentIntake({
    required String content,
    String source = 'voice',
    String? projectHint,
    int tokenBudget = 2000,
    bool useModel = false,
  }) async {
    processCalls += 1;
    lastContent = content;
    lastUsedModel = useModel;
    return ProcessingSubmissionResult(
      localRun: LocalProcessingRunSummary(
        id: 'run-1',
        project: 'BoxBrain',
        intent: 'build',
        status: 'completed',
        normalizedInput: content,
        steps: const [
          ProcessingStepSummary(
            agentId: 'orchestrator',
            status: 'completed',
            summary: 'Normalized and routed the intake.',
          ),
        ],
      ),
    );
  }
}

class _RemoteControllerApi extends _OnlineControllerApi {
  _RemoteControllerApi();

  int createCalls = 0;
  int probeCalls = 0;
  int openCalls = 0;
  int deleteCalls = 0;
  int proposeCalls = 0;
  int executeCalls = 0;
  String? lastDiagnosticGoal;
  final List<RemoteTargetSummary> remoteTargets = [
    RemoteTargetSummary(
      id: 'remote-usb',
      name: 'Kali Pi USB-C',
      transport: 'usb-c',
      host: '10.12.194.1',
      port: 22,
      username: 'kali',
      authorized: true,
      builtIn: true,
      status: 'online',
      credentialMode: 'dedicated-key',
      capabilities: const [
        'tcp-probe',
        'interactive-shell',
        'edge-diagnostics',
      ],
      lastCheckedAt: DateTime.utc(2026, 7, 28, 15),
      createdAt: DateTime.utc(2026, 7, 24, 12),
    ),
  ];

  @override
  Future<List<RemoteTargetSummary>> fetchRemoteTargets() async =>
      List.unmodifiable(remoteTargets);

  @override
  Future<RemoteTargetSummary> createRemoteTarget({
    required String name,
    required String transport,
    required String host,
    required int port,
    String? username,
    bool insecureTransportAcknowledged = false,
  }) async {
    createCalls += 1;
    final target = RemoteTargetSummary(
      id: 'remote-created',
      name: name,
      transport: transport,
      host: host,
      port: port,
      username: username,
      authorized: true,
      builtIn: false,
      status: 'unknown',
      credentialMode: 'ssh-agent',
      capabilities: const ['tcp-probe', 'interactive-shell'],
      lastCheckedAt: null,
      createdAt: DateTime.utc(2026, 7, 28, 16),
    );
    remoteTargets.add(target);
    return target;
  }

  @override
  Future<RemoteTargetProbeSummary> probeRemoteTarget(String targetId) async {
    probeCalls += 1;
    return RemoteTargetProbeSummary(
      targetId: targetId,
      status: 'online',
      resolvedAddress: '10.12.194.1',
      latencyMs: 4,
      message: 'USB-C endpoint is reachable.',
      checkedAt: DateTime.utc(2026, 7, 28, 16),
    );
  }

  @override
  Future<RemoteSessionSummary> openRemoteTargetSession({
    required String targetId,
    String? insecureConfirmation,
  }) async {
    openCalls += 1;
    return RemoteSessionSummary(
      targetId: targetId,
      status: 'opened',
      application: 'SSH terminal',
      message: 'Opened an operator-controlled SSH terminal session.',
    );
  }

  @override
  Future<DiagnosticProposalSummary> proposeRemoteDiagnostic({
    required String targetId,
    required String goal,
  }) async {
    proposeCalls += 1;
    lastDiagnosticGoal = goal;
    return DiagnosticProposalSummary(
      id: 'proposal-1',
      targetId: targetId,
      targetName: 'Kali Pi USB-C',
      goal: goal,
      plan: const DiagnosticPlanSummary(
        action: 'disk_usage',
        summary: 'Collect fixed read-only disk evidence.',
        expectedEvidence: 'Filesystem usage in bytes.',
        riskNote: 'Read-only; no files are changed.',
      ),
      status: 'pending',
      model: 'gpt-5.6-sol',
      providerTokens: 42,
      requiresConfirmation: true,
      createdAt: DateTime.utc(2026, 7, 28, 16),
      expiresAt: DateTime.utc(2026, 7, 28, 16, 10),
    );
  }

  @override
  Future<DiagnosticExecutionSummary> executeDiagnosticProposal(
    String proposalId,
  ) async {
    executeCalls += 1;
    return DiagnosticExecutionSummary(
      proposalId: proposalId,
      targetId: 'remote-usb',
      action: 'disk_usage',
      status: 'succeeded',
      exitCode: 0,
      output: '/dev/root 1000 400 600 40% /',
      truncated: false,
      durationMs: 25,
      executedAt: DateTime.utc(2026, 7, 28, 16, 1),
    );
  }

  @override
  Future<void> deleteRemoteTarget(String targetId) async {
    deleteCalls += 1;
    remoteTargets.removeWhere((target) => target.id == targetId);
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
  Future<List<RemoteTargetSummary>> fetchRemoteTargets() async => const [];

  @override
  Future<List<EdgeAgentSummary>> fetchEdgeAgents() async => const [];

  @override
  Future<List<TargetSummary>> fetchTargets() async => const [];
}
