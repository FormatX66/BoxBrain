import 'dart:async';

import 'package:flutter/material.dart';

import '../models/agent_models.dart';
import '../models/controller_status.dart';
import '../services/controller_api.dart';
import '../widgets/section_card.dart';
import '../widgets/stat_tile.dart';

class AgentOperationsScreen extends StatefulWidget {
  const AgentOperationsScreen({
    required this.api,
    required this.status,
    required this.active,
    super.key,
  });

  final ControllerApi api;
  final ControllerStatus status;
  final bool active;

  @override
  State<AgentOperationsScreen> createState() => _AgentOperationsScreenState();
}

class _AgentOperationsScreenState extends State<AgentOperationsScreen> {
  final _intakeController = TextEditingController();
  final _projectController = TextEditingController();

  List<ProcessingAgentSummary> _agents = const [];
  List<AgentTaskSummary> _tasks = const [];
  ModelRuntimeSummary? _runtime;
  AgentWorkspaceSummary? _workspace;
  ChatOrganizerSummary? _chatOrganizer;
  List<OrganizedChatSummary> _organizedChats = const [];
  ProcessingSubmissionResult? _lastResult;
  String _source = 'voice';
  String? _error;
  bool _loaded = false;
  bool _loading = false;
  bool _submitting = false;
  bool _useModel = false;

  @override
  void initState() {
    super.initState();
    if (widget.active) unawaited(_load());
  }

  @override
  void didUpdateWidget(covariant AgentOperationsScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.active && (!oldWidget.active || !_loaded)) {
      unawaited(_load());
    }
  }

  @override
  void dispose() {
    _intakeController.dispose();
    _projectController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (_loading || widget.status.connection != ConnectionStateLabel.online) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait<Object>([
        widget.api.fetchProcessingAgents(),
        widget.api.fetchModelRuntime(),
        widget.api.fetchAgentWorkspace(),
        widget.api.fetchChatOrganizer(),
        widget.api.fetchOrganizedChats(),
        widget.api.fetchAgentTasks(),
      ]);
      if (!mounted) return;
      setState(() {
        _agents = results[0] as List<ProcessingAgentSummary>;
        _runtime = results[1] as ModelRuntimeSummary;
        _workspace = results[2] as AgentWorkspaceSummary;
        _chatOrganizer = results[3] as ChatOrganizerSummary;
        _organizedChats = results[4] as List<OrganizedChatSummary>;
        _tasks = results[5] as List<AgentTaskSummary>;
        _loaded = true;
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submit() async {
    final content = _intakeController.text.trim();
    if (content.isEmpty || _submitting) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final result = await widget.api.processAgentIntake(
        content: content,
        source: _source,
        projectHint: _projectController.text,
        useModel: _useModel,
      );
      if (!mounted) return;
      setState(() => _lastResult = result);
      await _load();
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
      await _load();
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final runtime = _runtime;
    final workspace = _workspace;
    final online = widget.status.connection == ConnectionStateLabel.online;
    final modelReady = runtime?.ready ?? false;

    return RefreshIndicator(
      onRefresh: _load,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Processing agents',
                        style: Theme.of(context).textTheme.headlineMedium,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Turn rough voice notes into durable memory, tasks, '
                        'plans, and approval-gated handoffs.',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                    ],
                  ),
                ),
                IconButton.outlined(
                  tooltip: 'Refresh agents',
                  onPressed: online && !_loading ? _load : null,
                  icon: const Icon(Icons.refresh),
                ),
              ],
            ),
            if (_loading) ...[
              const SizedBox(height: 16),
              const LinearProgressIndicator(),
            ],
            if (_error != null) ...[
              const SizedBox(height: 16),
              _ErrorCallout(
                message: _error!,
                modelAttempted: _useModel,
                onUseLocal: () => setState(() => _useModel = false),
              ),
            ],
            const SizedBox(height: 20),
            SectionCard(
              title: 'New intake',
              subtitle: _useModel
                  ? 'OpenAI reasoning plus the durable local crew'
                  : 'Deterministic local processing - no provider tokens',
              trailing: Chip(
                avatar: Icon(
                  _useModel ? Icons.auto_awesome : Icons.offline_bolt,
                  size: 17,
                ),
                label: Text(_useModel ? 'Model' : 'Local'),
              ),
              child: Column(
                children: [
                  TextField(
                    key: const Key('agent-intake'),
                    controller: _intakeController,
                    minLines: 3,
                    maxLines: 7,
                    maxLength: 20000,
                    decoration: const InputDecoration(
                      labelText: 'Voice note or request',
                      hintText: 'Build the BoxBrain memory dashboard and keep '
                          'deployment approval-gated.',
                      border: OutlineInputBorder(),
                      alignLabelWithHint: true,
                    ),
                  ),
                  const SizedBox(height: 12),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final narrow = constraints.maxWidth < 620;
                      final source = DropdownButtonFormField<String>(
                        initialValue: _source,
                        decoration: const InputDecoration(
                          labelText: 'Source',
                          border: OutlineInputBorder(),
                        ),
                        items: const [
                          DropdownMenuItem(
                            value: 'voice',
                            child: Text('Voice'),
                          ),
                          DropdownMenuItem(
                            value: 'chat',
                            child: Text('Chat'),
                          ),
                          DropdownMenuItem(
                            value: 'api',
                            child: Text('API'),
                          ),
                          DropdownMenuItem(
                            value: 'file',
                            child: Text('File'),
                          ),
                        ],
                        onChanged: (value) {
                          if (value != null) setState(() => _source = value);
                        },
                      );
                      final project = TextField(
                        controller: _projectController,
                        decoration: const InputDecoration(
                          labelText: 'Project hint (optional)',
                          border: OutlineInputBorder(),
                        ),
                      );
                      if (narrow) {
                        return Column(
                          children: [
                            source,
                            const SizedBox(height: 12),
                            project,
                          ],
                        );
                      }
                      return Row(
                        children: [
                          SizedBox(width: 180, child: source),
                          const SizedBox(width: 12),
                          Expanded(child: project),
                        ],
                      );
                    },
                  ),
                  const SizedBox(height: 8),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Use model reasoning'),
                    subtitle: Text(
                      modelReady
                          ? '${runtime!.model} is configured. External actions '
                              'remain disabled.'
                          : 'Local mode remains available while the model '
                              'runtime is unavailable.',
                    ),
                    value: _useModel,
                    onChanged: modelReady
                        ? (value) => setState(() => _useModel = value)
                        : null,
                  ),
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.centerRight,
                    child: FilledButton.icon(
                      key: const Key('run-agent-crew'),
                      onPressed: online && !_submitting ? _submit : null,
                      icon: _submitting
                          ? const SizedBox.square(
                              dimension: 17,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                              ),
                            )
                          : Icon(
                              _useModel
                                  ? Icons.auto_awesome
                                  : Icons.account_tree,
                            ),
                      label: Text(
                        _submitting
                            ? 'Processing'
                            : _useModel
                                ? 'Run model orchestrator'
                                : 'Run local crew',
                      ),
                    ),
                  ),
                ],
              ),
            ),
            if (_lastResult != null) ...[
              const SizedBox(height: 20),
              _RunResultCard(result: _lastResult!),
            ],
            const SizedBox(height: 20),
            _RuntimeCard(runtime: runtime),
            if (workspace != null) ...[
              const SizedBox(height: 20),
              _WorkspaceStats(workspace: workspace),
            ],
            const SizedBox(height: 20),
            _ChatOrganizerCard(
              organizer: _chatOrganizer,
              chats: _organizedChats,
            ),
            const SizedBox(height: 20),
            SectionCard(
              title: 'The crew',
              subtitle: '${_agents.length} operational processing agents',
              child: _agents.isEmpty
                  ? const Text('Agent definitions are not available yet.')
                  : LayoutBuilder(
                      builder: (context, constraints) {
                        final width = constraints.maxWidth >= 1000
                            ? (constraints.maxWidth - 24) / 3
                            : constraints.maxWidth >= 640
                                ? (constraints.maxWidth - 12) / 2
                                : constraints.maxWidth;
                        return Wrap(
                          spacing: 12,
                          runSpacing: 12,
                          children: [
                            for (final agent in _agents)
                              SizedBox(
                                width: width,
                                child: _AgentCard(agent: agent),
                              ),
                          ],
                        );
                      },
                    ),
            ),
            const SizedBox(height: 20),
            SectionCard(
              title: 'Agent tasks',
              subtitle: '${_tasks.length} durable task records',
              child: _tasks.isEmpty
                  ? const Text(
                      'Run the crew to create the first project task.',
                    )
                  : Column(
                      children: [
                        for (final task in _tasks.take(12))
                          ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: Icon(_taskIcon(task.status)),
                            title: Text(task.title),
                            subtitle: Text(task.project),
                            trailing:
                                Chip(label: Text(_titleCase(task.status))),
                          ),
                      ],
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ChatOrganizerCard extends StatelessWidget {
  const _ChatOrganizerCard({
    required this.organizer,
    required this.chats,
  });

  final ChatOrganizerSummary? organizer;
  final List<OrganizedChatSummary> chats;

  @override
  Widget build(BuildContext context) {
    final value = organizer;
    final synced = value?.lastSyncAt != null;
    return SectionCard(
      title: 'ChatGPT organizer',
      subtitle: synced
          ? 'Indexed locally. Suggested moves stay read-only.'
          : 'Waiting for the first ChatGPT index sync.',
      trailing: Chip(
        avatar: Icon(
          synced ? Icons.check_circle : Icons.sync,
          size: 17,
        ),
        label: Text(synced ? 'Synced' : 'Not synced'),
      ),
      child: value == null || value.totalChatCount == 0
          ? const Text(
              'No chats are indexed yet. A sync adds titles and project '
              'metadata without copying private browser storage.',
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    Chip(label: Text('${value.totalChatCount} chats')),
                    Chip(
                      label: Text(
                        '${value.sourceProjectCount} ChatGPT projects',
                      ),
                    ),
                    Chip(label: Text('${value.pinnedCount} pinned')),
                    Chip(
                      label: Text(
                        '${value.suggestedMoveCount} suggested moves',
                      ),
                    ),
                    Chip(
                      label: Text('${value.unassignedCount} outside projects'),
                    ),
                  ],
                ),
                if (value.buckets.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  Text(
                    'File structure',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const SizedBox(height: 8),
                  Card(
                    clipBehavior: Clip.antiAlias,
                    child: Column(
                      children: [
                        for (final bucket in value.buckets)
                          ExpansionTile(
                            key: Key('chat-folder-${bucket.name}'),
                            leading: Icon(
                              bucket.isExistingChatGptProject
                                  ? Icons.folder
                                  : Icons.folder_outlined,
                            ),
                            title: Text(bucket.name),
                            trailing: Chip(
                              label: Text(bucket.chatCount.toString()),
                            ),
                            children: [
                              for (final chat in chats.where(
                                (item) => item.suggestedProject == bucket.name,
                              ))
                                ListTile(
                                  dense: true,
                                  leading: Icon(
                                    chat.pinnedIndex == null
                                        ? Icons.description_outlined
                                        : Icons.push_pin_outlined,
                                  ),
                                  title: Text(chat.title),
                                  subtitle: Text(
                                    chat.currentProject == null
                                        ? 'Ready to file'
                                        : 'Filed in ChatGPT',
                                  ),
                                  trailing: Chip(
                                    label: Text(chat.confidence),
                                  ),
                                ),
                              if (bucket.chatCount == 0)
                                const ListTile(
                                  dense: true,
                                  leading: Icon(Icons.inbox_outlined),
                                  title: Text('Empty folder'),
                                ),
                            ],
                          ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
    );
  }
}

class _RuntimeCard extends StatelessWidget {
  const _RuntimeCard({required this.runtime});

  final ModelRuntimeSummary? runtime;

  @override
  Widget build(BuildContext context) {
    final value = runtime;
    return SectionCard(
      title: 'Agent runtime',
      subtitle: value == null
          ? 'Waiting for controller status'
          : '${value.model} - ${value.executionMode}',
      trailing: Chip(
        avatar: Icon(
          value?.ready == true ? Icons.check_circle : Icons.info_outline,
          size: 17,
        ),
        label: Text(value?.ready == true ? 'Ready' : 'Local only'),
      ),
      child: Wrap(
        spacing: 10,
        runSpacing: 10,
        children: [
          _StatusChip(
            label: 'SDK',
            enabled: value?.sdkAvailable == true,
          ),
          _StatusChip(
            label: 'Credential',
            enabled: value?.configured == true,
          ),
          _StatusChip(
            label: 'Side effects disabled',
            enabled: value?.externalSideEffectsEnabled == false,
          ),
        ],
      ),
    );
  }
}

class _WorkspaceStats extends StatelessWidget {
  const _WorkspaceStats({required this.workspace});

  final AgentWorkspaceSummary workspace;

  @override
  Widget build(BuildContext context) {
    final items = [
      (
        'Projects',
        workspace.projectCount.toString(),
        Icons.folder_outlined,
      ),
      (
        'Memory records',
        workspace.memoryCount.toString(),
        Icons.memory,
      ),
      (
        'Open tasks',
        workspace.openTaskCount.toString(),
        Icons.checklist,
      ),
      (
        'Provider tokens',
        workspace.providerTokensUsed.toString(),
        Icons.data_usage,
      ),
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth >= 1000
            ? (constraints.maxWidth - 36) / 4
            : constraints.maxWidth >= 560
                ? (constraints.maxWidth - 12) / 2
                : constraints.maxWidth;
        return Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            for (final item in items)
              SizedBox(
                width: width,
                child: StatTile(
                  label: item.$1,
                  value: item.$2,
                  icon: item.$3,
                ),
              ),
          ],
        );
      },
    );
  }
}

class _AgentCard extends StatelessWidget {
  const _AgentCard({required this.agent});

  final ProcessingAgentSummary agent;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainerHigh,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(child: Icon(_agentIcon(agent.id))),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        agent.character,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      Text(
                        agent.name,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
                if (agent.enabled) const Icon(Icons.check_circle, size: 18),
              ],
            ),
            const SizedBox(height: 12),
            Text(agent.responsibility),
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final capability in agent.capabilities)
                  Chip(
                    visualDensity: VisualDensity.compact,
                    label: Text(capability),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _RunResultCard extends StatelessWidget {
  const _RunResultCard({required this.result});

  final ProcessingSubmissionResult result;

  @override
  Widget build(BuildContext context) {
    final run = result.localRun;
    final plan = result.plan;
    return SectionCard(
      title: 'Latest result',
      subtitle: '${run.project} - ${_titleCase(run.intent)}',
      trailing: Chip(
        label: Text(
          plan?.requiresApproval == true
              ? 'Approval required'
              : _titleCase(run.status.replaceAll('_', ' ')),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(plan?.summary ?? run.normalizedInput),
          if (plan != null && plan.tasks.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('Planned tasks',
                style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 6),
            for (final task in plan.tasks)
              Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text('- $task'),
              ),
          ],
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final step in run.steps)
                Chip(
                  avatar: Icon(
                    step.status == 'completed' ? Icons.check : Icons.schedule,
                    size: 16,
                  ),
                  label: Text(step.agentId),
                ),
            ],
          ),
          if (result.providerUsage != null) ...[
            const SizedBox(height: 12),
            Text(
              '${result.model} used '
              '${result.providerUsage!.totalTokens} provider tokens.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ],
      ),
    );
  }
}

class _ErrorCallout extends StatelessWidget {
  const _ErrorCallout({
    required this.message,
    required this.modelAttempted,
    required this.onUseLocal,
  });

  final String message;
  final bool modelAttempted;
  final VoidCallback onUseLocal;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(
              Icons.warning_amber,
              color: Theme.of(context).colorScheme.onErrorContainer,
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                message,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onErrorContainer,
                ),
              ),
            ),
            if (modelAttempted)
              TextButton(
                onPressed: onUseLocal,
                child: const Text('Use local crew'),
              ),
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.label, required this.enabled});

  final String label;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Chip(
      avatar: Icon(
        enabled ? Icons.check_circle : Icons.cancel_outlined,
        color: enabled
            ? Theme.of(context).colorScheme.primary
            : Theme.of(context).colorScheme.error,
        size: 17,
      ),
      label: Text(label),
    );
  }
}

IconData _agentIcon(String id) {
  return switch (id) {
    'orchestrator' => Icons.hub,
    'quartermaster' => Icons.inventory_2_outlined,
    'sentinel' => Icons.shield_outlined,
    'librarian' => Icons.local_library_outlined,
    'archivist' => Icons.archive_outlined,
    'scout' => Icons.travel_explore,
    'task-manager' => Icons.checklist,
    'architect' => Icons.account_tree_outlined,
    'engineer' => Icons.engineering_outlined,
    'integrator' => Icons.cable,
    _ => Icons.smart_toy_outlined,
  };
}

IconData _taskIcon(String status) {
  return switch (status) {
    'done' => Icons.task_alt,
    'dismissed' => Icons.cancel_outlined,
    _ => Icons.radio_button_unchecked,
  };
}

String _titleCase(String value) {
  if (value.isEmpty) return value;
  return '${value[0].toUpperCase()}${value.substring(1)}';
}
