import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../models/controller_status.dart';
import '../services/controller_api.dart';
import '../widgets/section_card.dart';
import '../widgets/stat_tile.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({required this.api, super.key});

  final ControllerApi api;

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  static const _destinations = [
    NavigationRailDestination(
      icon: Icon(Icons.space_dashboard_outlined),
      selectedIcon: Icon(Icons.space_dashboard),
      label: Text('Dashboard'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.desktop_windows_outlined),
      selectedIcon: Icon(Icons.desktop_windows),
      label: Text('Target'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.task_alt_outlined),
      selectedIcon: Icon(Icons.task_alt),
      label: Text('Tasks'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.policy_outlined),
      selectedIcon: Icon(Icons.policy),
      label: Text('Policies'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.extension_outlined),
      selectedIcon: Icon(Icons.extension),
      label: Text('Plugins'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.receipt_long_outlined),
      selectedIcon: Icon(Icons.receipt_long),
      label: Text('Logs'),
    ),
  ];

  ControllerStatus _status = const ControllerStatus.connecting();
  List<TaskSummary> _tasks = const [];
  List<PolicySummary> _policies = const [];
  List<PluginSummary> _plugins = const [];
  List<TargetSummary> _targets = const [];
  List<EdgeAgentSummary> _edgeAgents = const [];
  List<AuditEventSummary> _events = const [];
  EmergencyStopState _emergencyStop = const EmergencyStopState.unknown();
  String? _error;
  bool _loading = true;
  bool _changingSafety = false;
  bool _eventsRefreshing = false;
  Timer? _liveTimer;
  Timer? _eventReconnectTimer;
  StreamSubscription<AuditEventSummary>? _eventSubscription;
  int _selectedIndex = 0;
  DateTime? _lastUpdated;

  @override
  void initState() {
    super.initState();
    unawaited(_initialize());
    _liveTimer = Timer.periodic(
      const Duration(seconds: 3),
      (_) => _refreshLiveState(),
    );
  }

  Future<void> _initialize() async {
    await _refresh();
    if (mounted) _startEventStream();
  }

  @override
  void dispose() {
    _liveTimer?.cancel();
    _eventReconnectTimer?.cancel();
    unawaited(_eventSubscription?.cancel());
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
      if (_status.connection == ConnectionStateLabel.offline) {
        _status = const ControllerStatus.connecting();
      }
    });

    try {
      final results = await Future.wait<Object>([
        widget.api.fetchHealth(),
        widget.api.fetchTasks(),
        widget.api.fetchPolicies(),
        widget.api.fetchPlugins(),
        widget.api.fetchTargets(),
        widget.api.fetchEdgeAgents(),
        widget.api.fetchEmergencyStop(),
        widget.api.fetchEvents(),
      ]);
      if (!mounted) return;

      final health = results[0] as ControllerHealth;
      final tasks = results[1] as List<TaskSummary>;
      final policies = results[2] as List<PolicySummary>;
      final plugins = results[3] as List<PluginSummary>;
      final targets = results[4] as List<TargetSummary>;
      final edgeAgents = results[5] as List<EdgeAgentSummary>;
      final emergencyStop = results[6] as EmergencyStopState;
      final events = results[7] as List<AuditEventSummary>;
      final activeTasks = tasks
          .where((task) => task.status == 'queued' || task.status == 'running')
          .length;
      final safePolicy =
          policies.where((policy) => policy.name == 'safe').firstOrNull;

      setState(() {
        _tasks = tasks;
        _policies = policies;
        _plugins = plugins;
        _targets = targets;
        _edgeAgents = edgeAgents;
        _emergencyStop = emergencyStop;
        _events = events;
        _status = ControllerStatus.online(
          activeTasks: activeTasks,
          enabledPlugins: plugins.where((plugin) => plugin.enabled).length,
          policyProfile: _titleCase(safePolicy?.name ?? 'safe'),
          version: health.version,
          environment: _titleCase(health.environment),
          executorEnabled: health.executorEnabled,
          authenticationRequired: health.authenticationRequired,
          eventStreamEnabled: health.eventStreamEnabled,
        );
        _loading = false;
        _lastUpdated = DateTime.now();
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _status = const ControllerStatus.offline();
        _error = error.toString();
        _loading = false;
      });
    }
  }

  Future<void> _refreshEvents() async {
    if (_eventsRefreshing ||
        _status.connection != ConnectionStateLabel.online) {
      return;
    }
    _eventsRefreshing = true;
    try {
      final events = await widget.api.fetchEvents();
      if (mounted) setState(() => _events = events);
    } catch (_) {
      // The full refresh surface reports controller connection errors.
    } finally {
      _eventsRefreshing = false;
    }
  }

  Future<void> _refreshLiveState() async {
    if (_status.connection != ConnectionStateLabel.online) return;
    try {
      final results = await Future.wait<Object>([
        widget.api.fetchEmergencyStop(),
        widget.api.fetchTargets(),
        widget.api.fetchEdgeAgents(),
      ]);
      if (mounted) {
        setState(() {
          _emergencyStop = results[0] as EmergencyStopState;
          _targets = results[1] as List<TargetSummary>;
          _edgeAgents = results[2] as List<EdgeAgentSummary>;
        });
      }
    } catch (_) {
      // The full refresh surface reports controller connection errors.
    }
  }

  void _startEventStream() {
    if (!mounted) return;
    _eventReconnectTimer?.cancel();
    unawaited(_eventSubscription?.cancel());
    final afterSequence = _events.fold<int>(
      0,
      (latest, event) => event.sequence > latest ? event.sequence : latest,
    );
    _eventSubscription =
        widget.api.streamEvents(afterSequence: afterSequence).listen(
              _acceptStreamEvent,
              onError: (Object _, StackTrace __) => _scheduleEventReconnect(),
              onDone: _scheduleEventReconnect,
              cancelOnError: true,
            );
  }

  void _acceptStreamEvent(AuditEventSummary event) {
    if (!mounted || _events.any((item) => item.sequence == event.sequence)) {
      return;
    }
    final events = [event, ..._events]
      ..sort((left, right) => right.sequence.compareTo(left.sequence));
    setState(() {
      _events = events.take(100).toList(growable: false);
      _lastUpdated = DateTime.now();
    });
  }

  void _scheduleEventReconnect() {
    if (!mounted) return;
    _eventReconnectTimer?.cancel();
    _eventReconnectTimer = Timer(
      const Duration(seconds: 2),
      _startEventStream,
    );
  }

  Future<void> _toggleEmergencyStop() async {
    if (_changingSafety || _status.connection != ConnectionStateLabel.online) {
      return;
    }

    final confirmed = _emergencyStop.engaged
        ? await showDialog<bool>(
            context: context,
            builder: (context) => const _EmergencyStopResetDialog(),
          )
        : await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
              icon: Icon(
                Icons.stop_circle_outlined,
                color: Theme.of(context).colorScheme.error,
                size: 42,
              ),
              title: const Text('Engage emergency stop?'),
              content: const Text(
                'This blocks Sandbox launches and all future executor actions. '
                'Read-only observation remains available.',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Cancel'),
                ),
                FilledButton.icon(
                  style: FilledButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.error,
                    foregroundColor: Theme.of(context).colorScheme.onError,
                  ),
                  onPressed: () => Navigator.pop(context, true),
                  icon: const Icon(Icons.stop_circle),
                  label: const Text('Stop actions'),
                ),
              ],
            ),
          );
    if (confirmed != true || !mounted) return;

    setState(() => _changingSafety = true);
    try {
      final state = _emergencyStop.engaged
          ? await widget.api.resetEmergencyStop()
          : await widget.api.engageEmergencyStop();
      if (!mounted) return;
      setState(() => _emergencyStop = state);
      await _refresh();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString())),
      );
    } finally {
      if (mounted) setState(() => _changingSafety = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      _Overview(
        status: _status,
        emergencyStop: _emergencyStop,
        tasks: _tasks,
        target: _targets.firstOrNull,
        edgeAgent: _edgeAgents.firstOrNull,
        error: _error,
        loading: _loading,
        onRetry: _refresh,
        onViewTarget: () => _selectDestination(1),
      ),
      _TargetSection(
        target: _targets.firstOrNull,
        status: _status,
        emergencyStop: _emergencyStop,
        api: widget.api,
        onRefresh: _refresh,
      ),
      _TaskSection(
        tasks: _tasks,
        targets: _targets,
        policies: _policies,
        status: _status,
        api: widget.api,
        onRefresh: _refresh,
      ),
      _PolicySection(
        policies: _policies,
        status: _status,
        onRefresh: _refresh,
      ),
      _PluginSection(
        plugins: _plugins,
        status: _status,
        onRefresh: _refresh,
      ),
      _LogSection(
        events: _events,
        status: _status,
        lastUpdated: _lastUpdated,
        error: _error,
        onRefresh: _refreshEvents,
      ),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth >= 900;
        return Scaffold(
          appBar: wide
              ? null
              : AppBar(
                  title: const Text('BoxBrain'),
                  actions: [
                    _EmergencyStopControl(
                      state: _emergencyStop,
                      busy: _changingSafety,
                      compact: true,
                      onPressed:
                          _status.connection == ConnectionStateLabel.online
                              ? _toggleEmergencyStop
                              : null,
                    ),
                    const SizedBox(width: 8),
                    _ConnectionBadge(
                      status: _status,
                      loading: _loading,
                      onRetry: _refresh,
                    ),
                    const SizedBox(width: 16),
                  ],
                ),
          body: Row(
            children: [
              if (wide)
                NavigationRail(
                  extended: constraints.maxWidth >= 1180,
                  minExtendedWidth: 210,
                  leading: const Padding(
                    padding: EdgeInsets.fromLTRB(12, 22, 12, 28),
                    child: _Brand(),
                  ),
                  trailing: Expanded(
                    child: Align(
                      alignment: Alignment.bottomCenter,
                      child: Padding(
                        padding: const EdgeInsets.only(bottom: 20),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            _EmergencyStopControl(
                              state: _emergencyStop,
                              busy: _changingSafety,
                              compact: constraints.maxWidth < 1180,
                              onPressed: _status.connection ==
                                      ConnectionStateLabel.online
                                  ? _toggleEmergencyStop
                                  : null,
                            ),
                            const SizedBox(height: 12),
                            _ConnectionBadge(
                              status: _status,
                              loading: _loading,
                              onRetry: _refresh,
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  destinations: _destinations,
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: _selectDestination,
                ),
              Expanded(
                child: Column(
                  children: [
                    if (_emergencyStop.engaged)
                      _EmergencyStopBanner(state: _emergencyStop),
                    Expanded(
                      child: IndexedStack(
                        index: _selectedIndex,
                        children: pages,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          bottomNavigationBar: wide
              ? null
              : NavigationBar(
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: _selectDestination,
                  destinations: _destinations
                      .map(
                        (destination) => NavigationDestination(
                          icon: destination.icon,
                          selectedIcon: destination.selectedIcon,
                          label: (destination.label as Text).data!,
                        ),
                      )
                      .toList(),
                ),
        );
      },
    );
  }

  void _selectDestination(int index) {
    setState(() => _selectedIndex = index);
  }
}

class _Brand extends StatelessWidget {
  const _Brand();

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.hub, color: Theme.of(context).colorScheme.primary, size: 30),
        const SizedBox(width: 10),
        Text('BoxBrain', style: Theme.of(context).textTheme.titleLarge),
      ],
    );
  }
}

class _EmergencyStopControl extends StatelessWidget {
  const _EmergencyStopControl({
    required this.state,
    required this.busy,
    required this.compact,
    required this.onPressed,
  });

  final EmergencyStopState state;
  final bool busy;
  final bool compact;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final tooltip = state.engaged ? 'Reset emergency stop' : 'Emergency stop';
    final icon = busy
        ? const SizedBox.square(
            dimension: 17,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        : Icon(state.engaged ? Icons.stop_circle : Icons.stop_circle_outlined);
    final action = busy ? null : onPressed;

    if (compact) {
      return state.engaged
          ? IconButton.filled(
              tooltip: tooltip,
              style: IconButton.styleFrom(
                backgroundColor: colors.error,
                foregroundColor: colors.onError,
              ),
              onPressed: action,
              icon: icon,
            )
          : IconButton.outlined(
              tooltip: tooltip,
              style: IconButton.styleFrom(foregroundColor: colors.error),
              onPressed: action,
              icon: icon,
            );
    }

    return state.engaged
        ? FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: colors.error,
              foregroundColor: colors.onError,
            ),
            onPressed: action,
            icon: icon,
            label: const Text('STOPPED'),
          )
        : OutlinedButton.icon(
            style: OutlinedButton.styleFrom(foregroundColor: colors.error),
            onPressed: action,
            icon: icon,
            label: const Text('Emergency stop'),
          );
  }
}

class _EmergencyStopBanner extends StatelessWidget {
  const _EmergencyStopBanner({required this.state});

  final EmergencyStopState state;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Material(
      color: colors.errorContainer,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
        child: Row(
          children: [
            Icon(Icons.stop_circle, color: colors.error),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Emergency stop engaged',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  Text(
                    state.reason ?? 'Effectful controller actions are blocked.',
                  ),
                ],
              ),
            ),
            if (MediaQuery.sizeOf(context).width >= 600)
              Text('Safety generation ${state.generation}'),
          ],
        ),
      ),
    );
  }
}

class _EmergencyStopResetDialog extends StatefulWidget {
  const _EmergencyStopResetDialog();

  @override
  State<_EmergencyStopResetDialog> createState() =>
      _EmergencyStopResetDialogState();
}

class _EmergencyStopResetDialogState extends State<_EmergencyStopResetDialog> {
  final _controller = TextEditingController();
  bool _confirmed = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      icon: Icon(
        Icons.lock_reset,
        color: Theme.of(context).colorScheme.error,
        size: 42,
      ),
      title: const Text('Reset emergency stop'),
      content: SizedBox(
        width: 420,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Only reset after you have verified the target and controller are safe. '
              'Type RESET to continue.',
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _controller,
              autofocus: true,
              decoration: const InputDecoration(
                labelText: 'Confirmation',
                border: OutlineInputBorder(),
              ),
              onChanged: (value) {
                setState(() => _confirmed = value.trim() == 'RESET');
              },
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Keep stopped'),
        ),
        FilledButton.icon(
          onPressed: _confirmed ? () => Navigator.pop(context, true) : null,
          icon: const Icon(Icons.lock_reset),
          label: const Text('Reset stop'),
        ),
      ],
    );
  }
}

class _ConnectionBadge extends StatelessWidget {
  const _ConnectionBadge({
    required this.status,
    required this.loading,
    required this.onRetry,
  });

  final ControllerStatus status;
  final bool loading;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (status.connection) {
      ConnectionStateLabel.online => ('Online', Colors.greenAccent),
      ConnectionStateLabel.connecting => ('Connecting', Colors.amberAccent),
      ConnectionStateLabel.offline => ('Offline', Colors.orange),
    };

    return Semantics(
      label: 'Controller $label',
      button: true,
      child: Tooltip(
        message: loading ? 'Checking controller' : 'Refresh controller data',
        child: ActionChip(
          avatar: loading
              ? const SizedBox.square(
                  dimension: 12,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Icon(Icons.circle, color: color, size: 10),
          label: Text(label),
          onPressed: loading ? null : onRetry,
          side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
        ),
      ),
    );
  }
}

class _Overview extends StatelessWidget {
  const _Overview({
    required this.status,
    required this.emergencyStop,
    required this.tasks,
    required this.target,
    required this.edgeAgent,
    required this.error,
    required this.loading,
    required this.onRetry,
    required this.onViewTarget,
  });

  final ControllerStatus status;
  final EmergencyStopState emergencyStop;
  final List<TaskSummary> tasks;
  final TargetSummary? target;
  final EdgeAgentSummary? edgeAgent;
  final String? error;
  final bool loading;
  final VoidCallback onRetry;
  final VoidCallback onViewTarget;

  @override
  Widget build(BuildContext context) {
    final online = status.connection == ConnectionStateLabel.online;
    final controllerValue = switch (status.connection) {
      ConnectionStateLabel.online => 'Online',
      ConnectionStateLabel.connecting => 'Checking',
      ConnectionStateLabel.offline => 'Offline',
    };
    final controllerColor = online ? Colors.greenAccent : Colors.orange;

    return RefreshIndicator(
      onRefresh: () async => onRetry(),
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(28),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1300),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Mission control',
                            style: Theme.of(context).textTheme.headlineMedium,
                          ),
                          const SizedBox(height: 6),
                          Text(
                            'Observe, queue, and audit work on isolated targets.',
                            style: Theme.of(context).textTheme.bodyLarge,
                          ),
                        ],
                      ),
                    ),
                    IconButton.filledTonal(
                      tooltip: 'Refresh controller data',
                      onPressed: loading ? null : onRetry,
                      icon: const Icon(Icons.refresh),
                    ),
                  ],
                ),
                if (error != null) ...[
                  const SizedBox(height: 18),
                  _ErrorBanner(message: error!, onRetry: onRetry),
                ],
                const SizedBox(height: 24),
                GridView.count(
                  crossAxisCount:
                      MediaQuery.sizeOf(context).width >= 1050 ? 4 : 2,
                  crossAxisSpacing: 14,
                  mainAxisSpacing: 14,
                  childAspectRatio: 2.2,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  children: [
                    StatTile(
                      label: 'Controller',
                      value: controllerValue,
                      icon: Icons.power_settings_new,
                      accent: controllerColor,
                    ),
                    StatTile(
                      label: 'Active tasks',
                      value: status.activeTasks.toString(),
                      icon: Icons.task_alt,
                    ),
                    StatTile(
                      label: 'Enabled plugins',
                      value: status.enabledPlugins.toString(),
                      icon: Icons.extension,
                    ),
                    StatTile(
                      label: 'Policy profile',
                      value: status.policyProfile,
                      icon: Icons.shield_outlined,
                      accent: Colors.greenAccent,
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                _OverviewCards(
                  status: status,
                  emergencyStop: emergencyStop,
                  tasks: tasks,
                  target: target,
                  edgeAgent: edgeAgent,
                  onViewTarget: onViewTarget,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _OverviewCards extends StatelessWidget {
  const _OverviewCards({
    required this.status,
    required this.emergencyStop,
    required this.tasks,
    required this.target,
    required this.edgeAgent,
    required this.onViewTarget,
  });

  final ControllerStatus status;
  final EmergencyStopState emergencyStop;
  final List<TaskSummary> tasks;
  final TargetSummary? target;
  final EdgeAgentSummary? edgeAgent;
  final VoidCallback onViewTarget;

  @override
  Widget build(BuildContext context) {
    final online = status.connection == ConnectionStateLabel.online;
    final cards = [
      SectionCard(
        title: 'Controller details',
        subtitle: online ? 'Live API response' : 'Waiting for controller',
        child: _PlaceholderRows(
          rows: [
            ('Version', status.version),
            ('Environment', status.environment),
            ('Executor', status.executorEnabled ? 'Enabled' : 'Disabled'),
            (
              'Authentication',
              status.authenticationRequired ? 'Token required' : 'Disabled',
            ),
            (
              'Audit updates',
              status.eventStreamEnabled ? 'Live stream' : 'Manual refresh',
            ),
          ],
        ),
      ),
      SectionCard(
        title: 'Task queue',
        subtitle: online ? 'Live controller queue' : 'Controller unavailable',
        child: _Callout(
          icon: Icons.inbox_outlined,
          title:
              tasks.isEmpty ? 'Queue is empty' : '${tasks.length} tasks found',
          message: status.executorEnabled
              ? 'Executor is enabled for approved tasks.'
              : 'The alpha accepts tasks but executes nothing yet.',
        ),
      ),
      SectionCard(
        title: 'Target',
        subtitle: target?.observationStatus == 'unavailable'
            ? 'Observer plugin unavailable'
            : target?.connected == true
                ? 'Out-of-process observation active'
                : 'Windows Sandbox not detected',
        trailing: FilledButton.icon(
          onPressed: target?.connected == true ||
                  (target?.startEnabled == true && !emergencyStop.engaged)
              ? onViewTarget
              : null,
          icon: Icon(
            target?.connected == true
                ? Icons.visibility_outlined
                : Icons.play_arrow,
          ),
          label: Text(target?.connected == true ? 'View' : 'Open'),
        ),
        child: _PlaceholderRows(
          rows: [
            ('Connection', target?.connected == true ? 'Connected' : 'Offline'),
            (
              'Transport',
              target?.observerProcessBoundary == 'out-of-process'
                  ? 'Out-of-process plugin'
                  : 'Unavailable',
            ),
            ('Access', 'Read-only; no input capability'),
          ],
        ),
      ),
      SectionCard(
        title: 'Kali Pi edge agent',
        subtitle: edgeAgent?.connected == true
            ? 'Connected through local SSH tunnel'
            : 'Local SSH tunnel not detected',
        child: _PlaceholderRows(
          rows: [
            (
              'Connection',
              edgeAgent?.connected == true ? 'Connected' : 'Offline'
            ),
            ('Version', edgeAgent?.version ?? 'Unavailable'),
            ('Host', edgeAgent?.hostname ?? 'Unavailable'),
            ('Authorized targets', '${edgeAgent?.targetCount ?? 0}'),
            ('Enrollment', 'USB-C auto + authorized SSH/Wi-Fi'),
            ('Pi network', edgeAgent?.networkInterface ?? 'Unavailable'),
            (
              'Saved-key audit',
              _wifiAuditLabel(edgeAgent?.wifiCredentialAudit ?? 'unavailable'),
            ),
            (
              'Recommendations',
              '${edgeAgent?.recommendationCount ?? 0}',
            ),
            ('Access', 'Read-only advisory over SSH'),
          ],
        ),
      ),
      SectionCard(
        title: 'Safety state',
        subtitle: 'Containment and logging remain mandatory',
        child: _PlaceholderRows(
          rows: [
            ('Profile', status.policyProfile),
            ('Target allowlist', 'Required'),
            ('Emergency stop', emergencyStop.engaged ? 'ENGAGED' : 'Ready'),
          ],
        ),
      ),
    ];

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 820) {
          return Column(
            children: [
              for (final card in cards) ...[card, const SizedBox(height: 14)],
            ],
          );
        }
        return GridView.count(
          crossAxisCount: 2,
          crossAxisSpacing: 14,
          mainAxisSpacing: 14,
          childAspectRatio: 1.55,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          children: cards,
        );
      },
    );
  }
}

class _TargetSection extends StatefulWidget {
  const _TargetSection({
    required this.target,
    required this.status,
    required this.emergencyStop,
    required this.api,
    required this.onRefresh,
  });

  final TargetSummary? target;
  final ControllerStatus status;
  final EmergencyStopState emergencyStop;
  final ControllerApi api;
  final VoidCallback onRefresh;

  @override
  State<_TargetSection> createState() => _TargetSectionState();
}

class _TargetSectionState extends State<_TargetSection> {
  Timer? _timer;
  Uint8List? _frame;
  bool _frameLoading = false;
  String? _frameError;
  bool _launching = false;
  String? _launchError;

  @override
  void initState() {
    super.initState();
    _updateTimer();
  }

  @override
  void didUpdateWidget(covariant _TargetSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.target?.connected != widget.target?.connected) {
      _updateTimer();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _updateTimer() {
    _timer?.cancel();
    if (widget.target?.connected != true) {
      _frame = null;
      _frameError = null;
      return;
    }
    _refreshFrame();
    _timer = Timer.periodic(
      const Duration(seconds: 2),
      (_) => _refreshFrame(),
    );
  }

  Future<void> _refreshFrame() async {
    if (_frameLoading || widget.target?.connected != true) return;
    _frameLoading = true;
    try {
      final frame = await widget.api.fetchSandboxFrame(
        cacheKey: DateTime.now().millisecondsSinceEpoch,
      );
      if (!mounted) return;
      setState(() {
        _frame = frame;
        _frameError = null;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => _frameError = error.toString());
    } finally {
      _frameLoading = false;
    }
  }

  Future<void> _startSandbox() async {
    setState(() {
      _launching = true;
      _launchError = null;
    });
    try {
      await widget.api.startSandbox();
      if (!mounted) return;
      widget.onRefresh();
      await Future<void>.delayed(const Duration(seconds: 2));
      if (!mounted) return;
      widget.onRefresh();
      setState(() => _launching = false);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _launching = false;
        _launchError = error.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.status.connection != ConnectionStateLabel.online) {
      return _UnavailableSection(onRetry: widget.onRefresh);
    }

    final target = widget.target;
    if (target == null || !target.connected) {
      return _SectionList(
        title: 'Windows Sandbox',
        subtitle: 'Read-only access only',
        onRefresh: widget.onRefresh,
        primaryAction:
            target?.startEnabled == true && !widget.emergencyStop.engaged
                ? FilledButton.icon(
                    onPressed: _launching ? null : _startSandbox,
                    icon: _launching
                        ? const SizedBox.square(
                            dimension: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.play_arrow),
                    label: Text(
                      _launching ? 'Opening Sandbox' : 'Open Windows Sandbox',
                    ),
                  )
                : null,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(22),
              child: _Callout(
                icon: widget.emergencyStop.engaged
                    ? Icons.stop_circle
                    : Icons.desktop_access_disabled,
                title: widget.emergencyStop.engaged
                    ? 'Emergency stop is engaged'
                    : target?.observationStatus == 'unavailable'
                        ? 'Observer plugin is unavailable'
                        : 'Windows Sandbox is not running',
                message: widget.emergencyStop.engaged
                    ? 'Reset the stop before opening the isolated test profile.'
                    : target?.observationStatus == 'unavailable'
                        ? 'The controller cannot verify the read-only target process.'
                        : 'Use the button above to open the isolated test profile.',
              ),
            ),
          ),
          if (target != null)
            Card(
              child: ListTile(
                leading: const Icon(Icons.auto_delete_outlined),
                title: const Text('Zero frame retention'),
                subtitle: Text(
                  'No frames are written to disk. '
                  '${target.observationPolicy.redactionRegionCount} configured '
                  'redaction regions; '
                  '${target.observationPolicy.maxFrameWidth} px max.',
                ),
              ),
            ),
          if (_launchError != null)
            Card(
              child: ListTile(
                leading: const Icon(Icons.error_outline),
                title: const Text('Sandbox did not open'),
                subtitle: Text(_launchError!),
              ),
            ),
        ],
      );
    }

    return _SectionList(
      title: target.name,
      subtitle: 'Live out-of-process window capture',
      onRefresh: widget.onRefresh,
      children: [
        SectionCard(
          title: 'Visual feed',
          subtitle: 'Refreshes every two seconds',
          trailing: const Chip(
            avatar: Icon(Icons.visibility_outlined, size: 16),
            label: Text('Read-only'),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: ColoredBox(
              color: Colors.black,
              child: AspectRatio(
                aspectRatio: 2.45,
                child: _frame != null
                    ? Image.memory(
                        _frame!,
                        fit: BoxFit.contain,
                        gaplessPlayback: true,
                      )
                    : _frameError != null
                        ? Center(
                            child: Padding(
                              padding: const EdgeInsets.all(20),
                              child: _Callout(
                                icon: Icons.image_not_supported_outlined,
                                title: 'Frame unavailable',
                                message: _frameError!,
                              ),
                            ),
                          )
                        : const Center(child: CircularProgressIndicator()),
              ),
            ),
          ),
        ),
        Card(
          child: ListTile(
            leading: const Icon(Icons.auto_delete_outlined),
            title: const Text('Zero frame retention'),
            subtitle: Text(
              'No frames are written to disk. '
              '${target.observationPolicy.redactionRegionCount} configured '
              'redaction regions; '
              '${target.observationPolicy.maxFrameWidth} px max.',
            ),
          ),
        ),
        Card(
          child: ListTile(
            leading: const Icon(Icons.account_tree_outlined),
            title: const Text('Observer runs out of process'),
            subtitle: Text(
              '${target.observerPluginId} has status and frame capabilities only.',
            ),
          ),
        ),
        const Card(
          child: ListTile(
            leading: Icon(Icons.lock_outline),
            title: Text('Observation mode is locked'),
            subtitle: Text(
              'BoxBrain cannot send input, clipboard data, files, or commands.',
            ),
          ),
        ),
        if (widget.emergencyStop.engaged)
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: const ListTile(
              leading: Icon(Icons.stop_circle),
              title: Text('Emergency stop engaged'),
              subtitle: Text(
                'Read-only observation remains available; actions are blocked.',
              ),
            ),
          ),
      ],
    );
  }
}

class _TaskSection extends StatelessWidget {
  const _TaskSection({
    required this.tasks,
    required this.targets,
    required this.policies,
    required this.status,
    required this.api,
    required this.onRefresh,
  });

  final List<TaskSummary> tasks;
  final List<TargetSummary> targets;
  final List<PolicySummary> policies;
  final ControllerStatus status;
  final ControllerApi api;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    if (status.connection != ConnectionStateLabel.online) {
      return _UnavailableSection(onRetry: onRefresh);
    }
    final target = targets.where((item) => item.connected).firstOrNull;
    return _SectionList(
      title: 'Tasks',
      subtitle: '${tasks.length} durable controller records',
      onRefresh: onRefresh,
      primaryAction: FilledButton.icon(
        onPressed: target == null || policies.isEmpty
            ? null
            : () => _showQueueDialog(context, target),
        icon: const Icon(Icons.add_task),
        label: const Text('Queue task'),
      ),
      children: tasks.isEmpty
          ? const [
              _Callout(
                icon: Icons.inbox_outlined,
                title: 'No tasks queued',
                message: 'Queue a goal for the read-only Windows Sandbox.',
              ),
            ]
          : tasks
              .map(
                (task) => Card(
                  child: ListTile(
                    leading: const Icon(Icons.task_alt),
                    title: Text(task.goal),
                    subtitle: Text(
                      '${task.targetId} - ${_titleCase(task.policyProfile)} policy',
                    ),
                    trailing: Chip(label: Text(_titleCase(task.status))),
                  ),
                ),
              )
              .toList(),
    );
  }

  Future<void> _showQueueDialog(
    BuildContext context,
    TargetSummary target,
  ) async {
    final created = await showDialog<bool>(
      context: context,
      builder: (context) => _QueueTaskDialog(
        api: api,
        target: target,
        policies: policies,
      ),
    );
    if (created == true) onRefresh();
  }
}

class _QueueTaskDialog extends StatefulWidget {
  const _QueueTaskDialog({
    required this.api,
    required this.target,
    required this.policies,
  });

  final ControllerApi api;
  final TargetSummary target;
  final List<PolicySummary> policies;

  @override
  State<_QueueTaskDialog> createState() => _QueueTaskDialogState();
}

class _QueueTaskDialogState extends State<_QueueTaskDialog> {
  final _formKey = GlobalKey<FormState>();
  final _goalController = TextEditingController();
  late String _policyProfile;
  bool _submitting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _policyProfile = widget.policies
            .where((policy) => policy.name == 'safe')
            .map((policy) => policy.name)
            .firstOrNull ??
        widget.policies.first.name;
  }

  @override
  void dispose() {
    _goalController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Queue a task'),
      content: SizedBox(
        width: 480,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextFormField(
                  controller: _goalController,
                  autofocus: true,
                  enabled: !_submitting,
                  minLines: 2,
                  maxLines: 5,
                  maxLength: 2000,
                  decoration: const InputDecoration(
                    labelText: 'Goal',
                    hintText: 'Describe what BoxBrain should plan and observe.',
                    border: OutlineInputBorder(),
                  ),
                  validator: (value) => value == null || value.trim().isEmpty
                      ? 'Enter a goal.'
                      : null,
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  initialValue: _policyProfile,
                  decoration: const InputDecoration(
                    labelText: 'Policy profile',
                    border: OutlineInputBorder(),
                  ),
                  items: widget.policies
                      .map(
                        (policy) => DropdownMenuItem(
                          value: policy.name,
                          child: Text(_titleCase(policy.name)),
                        ),
                      )
                      .toList(),
                  onChanged: _submitting
                      ? null
                      : (value) {
                          if (value != null) _policyProfile = value;
                        },
                ),
                const SizedBox(height: 16),
                Card(
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: Padding(
                    padding: const EdgeInsets.all(14),
                    child: _Callout(
                      icon: Icons.lock_outline,
                      title: widget.target.name,
                      message:
                          'This queues an audited plan only. The executor remains disabled.',
                    ),
                  ),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    _error!,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: _submitting ? null : () => Navigator.pop(context, false),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: _submitting ? null : _submit,
          icon: _submitting
              ? const SizedBox.square(
                  dimension: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.add_task),
          label: Text(_submitting ? 'Queueing' : 'Queue task'),
        ),
      ],
    );
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      await widget.api.createTask(
        goal: _goalController.text.trim(),
        targetId: widget.target.id,
        policyProfile: _policyProfile,
      );
      if (mounted) Navigator.pop(context, true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _submitting = false;
      });
    }
  }
}

class _PolicySection extends StatelessWidget {
  const _PolicySection({
    required this.policies,
    required this.status,
    required this.onRefresh,
  });

  final List<PolicySummary> policies;
  final ControllerStatus status;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    if (status.connection != ConnectionStateLabel.online) {
      return _UnavailableSection(onRetry: onRefresh);
    }
    return _SectionList(
      title: 'Policy profiles',
      subtitle: '${policies.length} profiles from the controller',
      onRefresh: onRefresh,
      children: policies
          .map(
            (policy) => Card(
              child: ListTile(
                leading: Icon(
                  policy.name == 'safe' ? Icons.verified_user : Icons.policy,
                ),
                title: Text(_titleCase(policy.name)),
                subtitle: Text(policy.description),
                trailing: Chip(
                  label: Text(
                    policy.confirmationsRequired ? 'Confirms' : 'Lab only',
                  ),
                ),
              ),
            ),
          )
          .toList(),
    );
  }
}

class _PluginSection extends StatelessWidget {
  const _PluginSection({
    required this.plugins,
    required this.status,
    required this.onRefresh,
  });

  final List<PluginSummary> plugins;
  final ControllerStatus status;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    if (status.connection != ConnectionStateLabel.online) {
      return _UnavailableSection(onRetry: onRefresh);
    }
    return _SectionList(
      title: 'Plugins',
      subtitle: '${plugins.length} discovered plugins',
      onRefresh: onRefresh,
      children: plugins.isEmpty
          ? const [
              _Callout(
                icon: Icons.extension_off,
                title: 'No plugins discovered',
                message:
                    'Add a valid plugin manifest to the plugins directory.',
              ),
            ]
          : plugins
              .map(
                (plugin) => Card(
                  child: ListTile(
                    leading: const Icon(Icons.extension),
                    title: Text(plugin.name),
                    subtitle: Text(
                      '${plugin.description} - v${plugin.version}\n'
                      '${plugin.processBoundary == 'out-of-process' ? 'Out of process' : 'Manifest only'} - '
                      '${plugin.capabilities.join(', ')}',
                    ),
                    trailing: Chip(
                      label: Text(plugin.enabled ? 'Enabled' : 'Disabled'),
                    ),
                  ),
                ),
              )
              .toList(),
    );
  }
}

class _LogSection extends StatelessWidget {
  const _LogSection({
    required this.events,
    required this.status,
    required this.lastUpdated,
    required this.error,
    required this.onRefresh,
  });

  final List<AuditEventSummary> events;
  final ControllerStatus status;
  final DateTime? lastUpdated;
  final String? error;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    final online = status.connection == ConnectionStateLabel.online;
    final eventCards = events
        .map(
          (event) => Card(
            child: ListTile(
              leading: CircleAvatar(child: Text('#${event.sequence}')),
              title: Text(event.message),
              subtitle: Text(
                '${event.targetId ?? 'Controller'} - ${_formatTime(event.createdAt)}',
              ),
              trailing: Chip(
                label: Text(
                  _titleCase(event.eventType
                      .replaceAll('.', ' ')
                      .replaceAll('_', ' ')),
                ),
              ),
            ),
          ),
        )
        .toList();
    return _SectionList(
      title: 'Audit log',
      subtitle: '${events.length} append-only controller events',
      onRefresh: onRefresh,
      children: [
        if (events.isEmpty)
          const _Callout(
            icon: Icons.history,
            title: 'No audit events yet',
            message: 'Queue a task to create the first durable event.',
          )
        else
          ...eventCards,
        Card(
          child: ListTile(
            leading: Icon(
              online ? Icons.check_circle : Icons.error_outline,
              color: online ? Colors.greenAccent : Colors.orange,
            ),
            title: Text(online ? 'Controller health check passed' : 'Offline'),
            subtitle: Text(
              error ??
                  (lastUpdated == null
                      ? 'No successful check yet.'
                      : 'Last updated ${_formatTime(lastUpdated!)}'),
            ),
          ),
        ),
      ],
    );
  }
}

class _SectionList extends StatelessWidget {
  const _SectionList({
    required this.title,
    required this.subtitle,
    required this.children,
    required this.onRefresh,
    this.primaryAction,
  });

  final String title;
  final String subtitle;
  final List<Widget> children;
  final VoidCallback? onRefresh;
  final Widget? primaryAction;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(28),
      children: [
        Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: Theme.of(context).textTheme.headlineMedium),
                  const SizedBox(height: 6),
                  Text(subtitle),
                ],
              ),
            ),
            if (primaryAction != null) ...[
              primaryAction!,
              const SizedBox(width: 8),
            ],
            if (onRefresh != null)
              IconButton.filledTonal(
                tooltip: 'Refresh',
                onPressed: onRefresh,
                icon: const Icon(Icons.refresh),
              ),
          ],
        ),
        const SizedBox(height: 22),
        ...children.expand((child) => [child, const SizedBox(height: 12)]),
      ],
    );
  }
}

class _UnavailableSection extends StatelessWidget {
  const _UnavailableSection({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.cloud_off,
              size: 54,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(height: 18),
            Text(
              'Controller unavailable',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            const Text('Start the backend, then try the connection again.'),
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Theme.of(context).colorScheme.errorContainer,
      borderRadius: BorderRadius.circular(14),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            const Icon(Icons.cloud_off),
            const SizedBox(width: 12),
            Expanded(child: Text(message)),
            TextButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}

class _PlaceholderRows extends StatelessWidget {
  const _PlaceholderRows({required this.rows});

  final List<(String, String)> rows;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        for (final row in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 7),
            child: Row(
              children: [
                Expanded(child: Text(row.$1)),
                Text(
                  row.$2,
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.outline),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _Callout extends StatelessWidget {
  const _Callout({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, color: Theme.of(context).colorScheme.primary),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(message),
            ],
          ),
        ),
      ],
    );
  }
}

String _titleCase(String value) {
  if (value.isEmpty) return value;
  return '${value[0].toUpperCase()}${value.substring(1)}';
}

String _wifiAuditLabel(String value) {
  return switch (value) {
    'blocked' => 'Blocked',
    'exposed' => 'EXPOSED',
    'not-run' => 'Not run',
    _ => 'Unavailable',
  };
}

String _formatTime(DateTime value) {
  final local = value.toLocal();
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  final second = local.second.toString().padLeft(2, '0');
  return '$hour:$minute:$second';
}
