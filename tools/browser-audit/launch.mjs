// Chrome launch options. Linux x64: the bundled Chromium from @sparticuz/chromium (WebGL via SwiftShader, no GPU needed).
// macOS/Windows or your own Chrome: set CHROME_PATH=/path/to/chrome.
export async function launchOptions(chromium) {
  if (process.env.CHROME_PATH) return { executablePath: process.env.CHROME_PATH, headless: true, args: ['--no-sandbox'] }
  return { executablePath: await chromium.executablePath(), headless: 'shell',
    args: [...chromium.args, '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] }
}
