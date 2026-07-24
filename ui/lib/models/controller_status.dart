enum ConnectionStateLabel { offline, connecting, online }

class ControllerStatus {
  const ControllerStatus({
    required this.connection,
    required this.activeTasks,
    required this.enabledPlugins,
    required this.policyProfile,
  });

  const ControllerStatus.offline()
      : connection = ConnectionStateLabel.offline,
        activeTasks = 0,
        enabledPlugins = 0,
        policyProfile = 'Safe';

  final ConnectionStateLabel connection;
  final int activeTasks;
  final int enabledPlugins;
  final String policyProfile;
}

