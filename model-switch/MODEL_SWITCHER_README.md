# Model Switcher for llama.cpp

This tool allows you to switch between different LLM models on the same port without restarting your application.

## Overview

The model switcher provides a way to replace the current model loaded in `llama-server.exe` with a different model. This is useful when you need to use specialized models for specific tasks while keeping the same API endpoint.

## How It Works

1. **Stops** the current `llama-server.exe` process
2. **Starts** a new instance with the specified model
3. **Waits** for the server to be ready
4. **Returns** control to your application

## Files

- `model_switcher.ps1` - Main PowerShell script
- `test_model_switcher.ps1` - Test script
- `model_manager.py` - Python wrapper for async applications

## Usage

### PowerShell (Command Line)

```powershell
# Switch to a different model
.\model_switcher.ps1 -Model "D:\models\specialized.gguf"

# Switch back to default
.\model_switcher.ps1 -Model "D:\models\nemotron.gguf"
```

### Python (Async Applications)

```python
from llm.model_manager import switch_model, switch_and_call

# Switch model
await switch_model("D:\models\specialized.gguf")

# Switch and call in one operation (auto-restores original model)
response = await switch_and_call(
    model_path="D:\models\specialized.gguf",
    system_prompt="You are a finance expert...",
    user_prompt="Analyze these transactions..."
)
```

### In Your Application

```python
# Example: Use specialized model for finance tasks
async def analyze_finance_data(transactions):
    """Analyze transactions using a finance-specialized model."""
    
    # Switch to finance model
    if not await switch_model("D:\models\phinance.gguf"):
        raise RuntimeError("Failed to switch to finance model")
    
    try:
        # Call the model
        prompt = f"Analyze these transactions: {transactions}"
        response = await call_orchestrator(
            system_prompt="You are a financial analyst...",
            user_prompt=prompt
        )
        return response
    finally:
        # Switch back to default model
        await switch_model("D:\models\nemotron.gguf")
```

## Configuration

Edit `model_switcher.ps1` to configure:

```powershell
$LLAMA_SERVER = "F:\work\vsoa1\soa\bin\llama-cuda\llama-server.exe"
$PORT = 8081
$CTX_SIZE = 4096
$THREADS = 8
$MAX_WAIT_SECONDS = 120
```

## Performance Characteristics

- **Switch time**: ~5-10 seconds (depends on model size)
- **VRAM**: Model is unloaded when server stops, freed when new model loads
- **Downtime**: Server is unavailable during switch
- **Reliability**: High - process replacement is more reliable than dynamic loading

## VRAM Management

The switcher automatically manages VRAM:

1. When you switch models, the old model's VRAM is freed
2. The new model loads into VRAM
3. Total VRAM usage remains similar (just different model)

Example with your setup:
- Nemotron: ~5.1 GB
- Phinance: ~2.4 GB
- Switching between them frees ~5.1 GB then uses ~2.4 GB

## Best Practices

1. **Minimize switches**: Each switch takes 5-10 seconds
2. **Use for specialized tasks**: Switch when you need specific capabilities
3. **Restore default**: Always switch back to default model when done
4. **Error handling**: Check return values and handle failures gracefully
5. **Monitor VRAM**: Use `nvidia-smi` to monitor memory usage

## Testing

Run the test script to verify everything works:

```powershell
.\test_model_switcher.ps1
```

This will:
1. Start with default model
2. Switch to alternative model (if available)
3. Switch back to default
4. Verify each step

## Troubleshooting

### Server doesn't start
- Check model path is correct
- Verify model file exists
- Check VRAM availability with `nvidia-smi`
- Look at logs in `$env:TEMP\llama_*.txt`

### Switch takes too long
- Increase `$MAX_WAIT_SECONDS` in config
- Check if model is corrupted
- Verify GPU is working properly

### Connection refused after switch
- Server may have failed to start
- Check error logs
- Verify model is compatible with your llama.cpp build

## Advanced Usage

### Multiple Ports

If you need multiple models simultaneously:

```powershell
# Port 8081 - Main model
llama-server.exe -m "nemotron.gguf" --port 8081

# Port 8082 - Specialized model
llama-server.exe -m "specialized.gguf" --port 8082
```

### Auto-Restore

The Python wrapper automatically restores the original model:

```python
# This will switch to specialized model, call it, then switch back
response = await switch_and_call(
    model_path="D:\models\specialized.gguf",
    system_prompt="...",
    user_prompt="..."
)
```

## Limitations

1. **Downtime**: Server is unavailable during switch (~5-10s)
2. **No hot-swap**: Model must be fully unloaded before new one loads
3. **Single port**: Only one model per port at a time
4. **Process-based**: Relies on process replacement, not dynamic loading

## Future Enhancements

Potential improvements:
- Add model warm-up/caching
- Implement health checks before switching
- Add metrics/logging for switch times
- Support for multiple ports in Python wrapper
