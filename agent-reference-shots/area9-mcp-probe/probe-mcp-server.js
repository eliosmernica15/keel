// Minimal zero-dependency MCP stdio probe server (research instrument only).
// Speaks JSON-RPC 2.0 over stdio: initialize, tools/list, tools/call,
// resources/list, resources/read, prompts/list, ping.
let buf = '';
process.stdin.on('data', (d) => {
  buf += d.toString();
  let i;
  while ((i = buf.indexOf('\n')) >= 0) {
    const line = buf.slice(0, i).trim();
    buf = buf.slice(i + 1);
    if (!line) continue;
    let msg;
    try { msg = JSON.parse(line); } catch { continue; }
    handle(msg);
  }
});

function send(o) { process.stdout.write(JSON.stringify(o) + '\n'); }

const LONG_NAME = 'x'.repeat(150);

function handle(msg) {
  if (msg.id === undefined) return; // notification
  const { id, method, params } = msg;

  if (method === 'initialize') {
    send({ jsonrpc: '2.0', id, result: {
      protocolVersion: params?.protocolVersion || '2025-06-18',
      capabilities: { tools: {}, resources: {}, prompts: {} },
      serverInfo: { name: 'probe-mcp', version: '0.0.1' }
    }});
    return;
  }

  if (method === 'tools/list') {
    send({ jsonrpc: '2.0', id, result: { tools: [
      { name: 'echo_text',
        description: 'Echoes back the given text. Probe tool for tool-name observation.',
        inputSchema: { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] } },
      { name: 'big_output',
        description: 'Returns a large text payload to observe output-limit behaviour.',
        inputSchema: { type: 'object', properties: { chars: { type: 'integer' } } } },
      { name: LONG_NAME,
        description: 'Tool with a very long name to probe the 128-character full-name limit.',
        inputSchema: { type: 'object', properties: {} } },
      { name: 'always_ask',
        description: 'Tool that must require approval on every call.',
        inputSchema: { type: 'object', properties: {} },
        _meta: { 'anthropic/requiresUserInteraction': true } }
    ]}});
    return;
  }

  if (method === 'tools/call') {
    const name = params?.name;
    if (name === 'big_output') {
      const n = Math.min(Number(params?.arguments?.chars) || 60000, 200000);
      send({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: 'X'.repeat(n) }] } });
    } else {
      send({ jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: 'ECHO:' + JSON.stringify(params?.arguments || {}) }] } });
    }
    return;
  }

  if (method === 'resources/list') {
    send({ jsonrpc: '2.0', id, result: { resources: [
      { uri: 'probe://file/readme.md', name: 'readme', mimeType: 'text/markdown' }
    ]}});
    return;
  }

  if (method === 'resources/read') {
    send({ jsonrpc: '2.0', id, result: { contents: [
      { uri: params?.uri, mimeType: 'text/markdown', text: '# Probe readme\nsanitized content' }
    ]}});
    return;
  }

  if (method === 'prompts/list') {
    send({ jsonrpc: '2.0', id, result: { prompts: [
      { name: 'hello', description: 'A probe prompt.', arguments: [] }
    ]}});
    return;
  }

  if (method === 'ping') { send({ jsonrpc: '2.0', id, result: {} }); return; }

  send({ jsonrpc: '2.0', id, error: { code: -32601, message: 'Method not found: ' + method } });
}
