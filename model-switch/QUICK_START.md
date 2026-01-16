# Model Switcher - Quick Start Guide

## 1. Install the Model Switcher

No installation needed! Just copy the files:

```powershell
# Copy to your scripts directory
cp model_switcher.ps1 test_model_switcher.ps1 MODEL_SWITCHER_README.md ..
```

## 2. Test It Works

```powershell
# Run the test script
.\test_model_switcher.ps1
```

This will:
- Start the default model (Nemotron)
- Switch to alternative model (if available)
- Switch back to default
- Verify everything works

## 3. Use It in Your Code

### Simple Usage (PowerShell)

```powershell
# Switch to a different model
.\model_switcher.ps1 -Model "D:\models\phinance.gguf"

# Do your work...

# Switch back
.\model_switcher.ps1 -Model "D:\models\nemotron.gguf"
```

### Advanced Usage (Python)

```python
from llm.model_manager import switch_and_call

# Switch model, call it, then switch back automatically
response = await switch_and_call(
    model_path="D:\models\phinance.gguf",
    system_prompt="You are a financial analyst...",
    user_prompt="Analyze these transactions..."
)
```

## 4. Example: Finance Task

```python
async def analyze_transactions(transactions):
    """Use finance model for transaction analysis."""
    
    # Switch to finance model
    if not await switch_model("D:\models\phinance.gguf"):
        # Fallback to default if switch fails
        return await call_orchestrator(
            "You are a general assistant...",
            f"Analyze: {transactions}"
        )
    
    try:
        # Use finance model
        response = await call_orchestrator(
            "You are a financial analyst...",
            f"Analyze: {transactions}"
        )
        return response
    finally:
        # Always switch back
        await switch_model("D:\models\nemotron.gguf")
```

## 5. Monitor VRAM

```powershell
# Check VRAM usage
nvidia-smi

# Or check continuously
nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits --loop=1
```

## 6. Troubleshooting

### Problem: Switch takes too long
- Check model path is correct
- Verify model file exists
- Check VRAM with `nvidia-smi`

### Problem: Server doesn't start
- Look at logs: `$env:TEMP\llama_*.txt`
- Check if model is corrupted
- Verify GPU is working

### Problem: Connection refused
- Server may have crashed
- Check error logs
- Try restarting manually

## 7. Need Help?

Read the full documentation:
- `MODEL_SWITCHER_README.md` - Complete guide
- `model_switcher.ps1` - Source code with comments

## That's it! 🎉

You now have model switching capability. Use it for:
- Specialized tasks (finance, coding, etc.)
- Testing different models
- Optimizing for specific workloads
