// Static server that serves the production build with the SAME security headers as frontend/nginx.conf (incl. the CSP).
import http from 'node:http'; import fs from 'node:fs'; import path from 'node:path'
const root = path.resolve(process.env.DIST_DIR ?? '../../frontend/dist-csp')
// read the policy straight from the nginx config so this test can never drift from what production sends
const csp = /Content-Security-Policy "([^"]+)"/.exec(fs.readFileSync(path.resolve('../../frontend/nginx.conf'), 'utf8'))?.[1]
if (!csp) throw new Error('could not find the CSP in frontend/nginx.conf')
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.json': 'application/json', '.webmanifest': 'application/manifest+json' }
http.createServer((req, res) => {
  const url = new URL(req.url, 'http://x'); let f = path.join(root, decodeURIComponent(url.pathname))
  if (!f.startsWith(root) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) f = path.join(root, 'index.html')
  res.writeHead(200, { 'content-type': types[path.extname(f)] || 'application/octet-stream', 'content-security-policy': csp, 'x-content-type-options': 'nosniff', 'x-frame-options': 'DENY', 'referrer-policy': 'no-referrer' })
  fs.createReadStream(f).pipe(res)
}).listen(4174, '127.0.0.1', () => console.log('csp server on 4174'))
