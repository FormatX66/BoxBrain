class AppConfig {
  const AppConfig._();

  static const controllerBaseUrl = String.fromEnvironment(
    'BOXBRAIN_API_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );
}
