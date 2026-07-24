import '../config/app_config.dart';

/// Defines controller endpoints without performing network calls yet.
///
/// A real transport will be added after authentication, retries, certificate
/// handling, and the API error model are agreed.
class ControllerApi {
  const ControllerApi({this.baseUrl = AppConfig.controllerBaseUrl});

  final String baseUrl;

  Uri endpoint(String path) {
    final normalized = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$baseUrl$normalized');
  }

  Uri get healthEndpoint => endpoint('/api/v1/health');
  Uri get tasksEndpoint => endpoint('/api/v1/tasks');
  Uri get policiesEndpoint => endpoint('/api/v1/policies');
  Uri get pluginsEndpoint => endpoint('/api/v1/plugins');
}

