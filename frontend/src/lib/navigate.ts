// A full page load to another path. Its own module so tests can mock it
// (jsdom does not let tests watch window.location.assign).
export function goTo(path: string): void {
  window.location.assign(path);
}
