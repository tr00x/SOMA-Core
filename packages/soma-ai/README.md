# soma-ai

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](../../LICENSE)

Behavioral monitoring SDK for TypeScript/JavaScript AI agents.

## Install

```bash
npm install soma-ai
```

## Quick Start

```typescript
import { SOMAEngine, quickstart, track } from "soma-ai";

const engine = quickstart({ agents: ["my-agent"] });

const t = track(engine, "my-agent", "generateText");
try {
  const result = await myLLMCall();
  t.setOutput(result);
  t.setTokens(result.usage.totalTokens);
} catch (e) {
  t.setError(true);
  throw e;
} finally {
  t.end();
}

console.log(t.result?.mode); // "OBSERVE" | "GUIDE" | "WARN" | "BLOCK"
```

## Documentation

See the [main SOMA repository](https://github.com/tr00x/soma) for full documentation, Python SDK, and Claude Code integration.

## License

MIT
