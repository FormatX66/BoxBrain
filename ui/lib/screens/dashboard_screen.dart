import 'dart:async';

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
  String? _error;
  bool _loading = true;
  int _selectedIndex = 0;
  DateTime? _lastUpdated;

  @override
  void initState() {
    super.initState();
    _refresh();
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
      ]);
      if (!mounted) return;

      final health = results[0] as ControllerHealth;
      final tasks = results[1] as List<TaskSummary>;
      final policies = results[2] as List<PolicySummary>;
      final plugins = results[3] as List<PluginSummary>;
      final targets = results[4] as List<TargetSummary>;
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
        _status = ControllerStatus.online(
          activeTasks: activeTasks,
          enabledPlugins: plugins.where((plugin) => plugin.enabled).length,
          policyProfile: _titleCase(safePolicy?.name ?? 'safe'),
          version: health.version,
          environment: _titleCase(health.environment),
          executorEnabled: health.executorEnabled,
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

  @override
  Widget build(BuildContext context) {
    final pages = [
      _Overview(
        status: _status,
        tasks: _tasks,
        target: _targets.firstOrNull,
        error: _error,
        loading: _loading,
        onRetry: _refresh,
        onViewTarget: () => _selectDestination(1),
      ),
      _TargetSection(
        target: _targets.firstOrNull,
        status: _status,
        api: widget.api,
        onRefresh: _refresh,
      ),
      _TaskSection(tasks: _tasks, status: _status, onRefresh: _refresh),
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
        status: _status,
        lastUpdated: _lastUpdated,
        error: _error,
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
                        child: _ConnectionBadge(
                          status: _status,
                          loading: _loading,
                          onRetry: _refresh,
                        ),
                      ),
                    ),
                  ),
                  destinations: _destinations,
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: _selectDestination,
                ),
              Expanded(
                child: IndexedStack(index: _selectedIndex, children: pages),
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
    required this.tasks,
    required this.target,
    required this.error,
    required this.loading,
    required this.onRetry,
    required this.onViewTarget,
  });

  final ControllerStatus status;
  final List<TaskSummary> tasks;
  final TargetSummary? target;
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
                  tasks: tasks,
                  target: target,
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
    required this.tasks,
    required this.target,
    required this.onViewTarget,
  });

  final ControllerStatus status;
  final List<TaskSummary> tasks;
  final TargetSummary? target;
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
        subtitle: target?.connected == true
            ? 'Local window capture active'
            : 'Windows Sandbox not detected',
        trailing: FilledButton.icon(
          onPressed: target?.connected == true ? onViewTarget : null,
          icon: const Icon(Icons.visibility_outlined),
          label: const Text('View'),
        ),
        child: _PlaceholderRows(
          rows: [
            ('Connection', target?.connected == true ? 'Connected' : 'Offline'),
            ('Transport', 'Local window capture'),
            ('Access', 'Read-only'),
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
            ('Emergency stop', 'Armed'),
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
    required this.api,
    required this.onRefresh,
  });

  final TargetSummary? target;
  final ControllerStatus status;
  final ControllerApi api;
  final VoidCallback onRefresh;

  @override
  State<_TargetSection> createState() => _TargetSectionState();
}

class _TargetSectionState extends State<_TargetSection> {
  Timer? _timer;
  int _frameVersion = DateTime.now().millisecondsSinceEpoch;

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
    if (widget.target?.connected != true) return;
    _timer = Timer.periodic(const Duration(seconds: 2), (_) {
      if (mounted) {
        setState(() => _frameVersion = DateTime.now().millisecondsSinceEpoch);
      }
    });
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
        children: const [
          Card(
            child: Padding(
              padding: EdgeInsets.all(22),
              child: _Callout(
                icon: Icons.desktop_access_disabled,
                title: 'Windows Sandbox is not running',
                message:
                    'Start the isolated Sandbox, then refresh this target.',
              ),
            ),
          ),
        ],
      );
    }

    final frameUri = widget.api.sandboxFrameEndpoint(cacheKey: _frameVersion);
    return _SectionList(
      title: target.name,
      subtitle: 'Live local window capture',
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
                child: Image.network(
                  frameUri.toString(),
                  fit: BoxFit.contain,
                  gaplessPlayback: true,
                  frameBuilder: (context, child, frame, synchronous) {
                    if (synchronous || frame != null) return child;
                    return const Center(child: CircularProgressIndicator());
                  },
                  errorBuilder: (context, error, stackTrace) {
                    return const Center(
                      child: Padding(
                        padding: EdgeInsets.all(20),
                        child: _Callout(
                          icon: Icons.image_not_supported_outlined,
                          title: 'Frame unavailable',
                          message:
                              'Refresh the target or reopen Windows Sandbox.',
                        ),
                      ),
                    );
                  },
                ),
              ),
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
      ],
    );
  }
}

class _TaskSection extends StatelessWidget {
  const _TaskSection({
    required this.tasks,
    required this.status,
    required this.onRefresh,
  });

  final List<TaskSummary> tasks;
  final ControllerStatus status;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    if (status.connection != ConnectionStateLabel.online) {
      return _UnavailableSection(onRetry: onRefresh);
    }
    return _SectionList(
      title: 'Tasks',
      subtitle: '${tasks.length} controller records',
      onRefresh: onRefresh,
      children: tasks.isEmpty
          ? const [
              _Callout(
                icon: Icons.inbox_outlined,
                title: 'No tasks queued',
                message: 'The controller is online and the queue is empty.',
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
                    subtitle:
                        Text('${plugin.description} - v${plugin.version}'),
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
    required this.status,
    required this.lastUpdated,
    required this.error,
  });

  final ControllerStatus status;
  final DateTime? lastUpdated;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final online = status.connection == ConnectionStateLabel.online;
    return _SectionList(
      title: 'Connection log',
      subtitle: 'Local dashboard events',
      onRefresh: null,
      children: [
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
  });

  final String title;
  final String subtitle;
  final List<Widget> children;
  final VoidCallback? onRefresh;

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

String _formatTime(DateTime value) {
  final local = value.toLocal();
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  final second = local.second.toString().padLeft(2, '0');
  return '$hour:$minute:$second';
}
