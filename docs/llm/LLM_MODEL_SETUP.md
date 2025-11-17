# LLM Model Setup Guide

This guide explains how to download, manage, and use LLM models for mCube Trading System.

## Directory Structure

```
models/
├── gguf/              # Downloaded GGUF model files
├── ollama/            # Ollama Modelfiles
└── metadata.json      # Model tracking metadata
```

## Quick Start

### Option 1: Automated Setup (Recommended)

```bash
python manage.py manage_models --quick-setup
```

This will:
1. Download DeepSeek Coder 6.7B (~3.8GB)
2. Import it into Ollama
3. Configure it for use

### Option 2: Manual Setup

1. **List recommended models**:
   ```bash
   python manage.py manage_models --list-recommended
   ```

2. **Download a model**:
   ```bash
   python manage.py manage_models --download \
       TheBloke/deepseek-coder-6.7B-instruct-GGUF \
       deepseek-coder-6.7b-instruct.Q4_K_M.gguf
   ```

3. **Import to Ollama**:
   ```bash
   python manage.py manage_models --import-to-ollama \
       deepseek-coder-6.7b-instruct.Q4_K_M.gguf \
       deepseek-coder-6.7b
   ```

4. **Update .env file**:
   ```env
   OLLAMA_MODEL=deepseek-coder-6.7b
   ```

## Recommended Models for Trading

### 1. DeepSeek Coder 6.7B Instruct (Q4_K_M) ⭐ Recommended
- **Size**: ~3.8GB
- **RAM Required**: 8GB
- **Best For**: General analysis, trade validation, code analysis
- **Repo**: `TheBloke/deepseek-coder-6.7B-instruct-GGUF`
- **File**: `deepseek-coder-6.7b-instruct.Q4_K_M.gguf`

**Why**: Best balance of performance and resource usage. Excellent for:
- Analyzing news and market data
- Validating trade setups
- Extracting structured information
- Code generation and analysis

**Download**:
```bash
python manage.py manage_models --download \
    TheBloke/deepseek-coder-6.7B-instruct-GGUF \
    deepseek-coder-6.7b-instruct.Q4_K_M.gguf
```

### 2. DeepSeek Coder 33B Instruct (Q4_K_M)
- **Size**: ~19GB
- **RAM Required**: 24GB
- **Best For**: Complex analysis, multi-step reasoning
- **Repo**: `TheBloke/deepseek-coder-33b-instruct-GGUF`
- **File**: `deepseek-coder-33b-instruct.Q4_K_M.gguf`

**Why**: More powerful reasoning capabilities. Use when:
- Deep market analysis is required
- Complex multi-factor decision making
- Detailed financial report analysis

### 3. Mistral 7B Instruct (Q4_K_M)
- **Size**: ~4.1GB
- **RAM Required**: 8GB
- **Best For**: Fast responses, sentiment analysis
- **Repo**: `TheBloke/Mistral-7B-Instruct-v0.2-GGUF`
- **File**: `mistral-7b-instruct-v0.2.Q4_K_M.gguf`

**Why**: Very fast inference. Good for:
- Quick sentiment analysis
- Real-time news processing
- Rapid queries

### 4. Llama 2 13B Chat (Q4_K_M)
- **Size**: ~7.4GB
- **RAM Required**: 12GB
- **Best For**: Conversational analysis
- **Repo**: `TheBloke/Llama-2-13B-chat-GGUF`
- **File**: `llama-2-13b-chat.Q4_K_M.gguf`

### 5. OpenHermes 2.5 Mistral 7B (Q4_K_M)
- **Size**: ~4.1GB
- **RAM Required**: 8GB
- **Best For**: Structured analysis, JSON extraction
- **Repo**: `TheBloke/OpenHermes-2.5-Mistral-7B-GGUF`
- **File**: `openhermes-2.5-mistral-7b.Q4_K_M.gguf`

## Understanding GGUF Quantization

GGUF files come in different quantization levels:

| Quantization | Size | Quality | Use Case |
|--------------|------|---------|----------|
| Q2_K | Smallest | Lower | Not recommended |
| Q3_K_M | Small | Medium | Budget option |
| **Q4_K_M** | **Medium** | **Good** | **Recommended** |
| Q5_K_M | Large | Better | High quality |
| Q6_K | Larger | Best | Maximum quality |
| Q8_0 | Largest | Highest | Near-original |

**Recommendation**: Use **Q4_K_M** for best balance of quality and size.

## Manual Download from Hugging Face

If you prefer to download manually:

1. **Visit Hugging Face**:
   ```
   https://huggingface.co/TheBloke/deepseek-coder-6.7B-instruct-GGUF
   ```

2. **Download GGUF file**:
   - Click on "Files and versions"
   - Find `deepseek-coder-6.7b-instruct.Q4_K_M.gguf`
   - Click download (or use `wget`/`curl`)

3. **Place in models directory**:
   ```bash
   mv deepseek-coder-6.7b-instruct.Q4_K_M.gguf models/gguf/
   ```

4. **Import to Ollama**:
   ```bash
   python manage.py manage_models --import-to-ollama \
       deepseek-coder-6.7b-instruct.Q4_K_M.gguf \
       deepseek-coder-6.7b
   ```

## Using `wget` or `curl`

### Using wget:
```bash
cd models/gguf/

wget https://huggingface.co/TheBloke/deepseek-coder-6.7B-instruct-GGUF/resolve/main/deepseek-coder-6.7b-instruct.Q4_K_M.gguf
```

### Using curl:
```bash
cd models/gguf/

curl -L -O https://huggingface.co/TheBloke/deepseek-coder-6.7B-instruct-GGUF/resolve/main/deepseek-coder-6.7b-instruct.Q4_K_M.gguf
```

## Managing Models

### List Local Models
```bash
python manage.py manage_models --list-local
```

### Delete a Model
```bash
python manage.py manage_models --delete <model-name>
```

### Check Ollama Models
```bash
ollama list
```

## Model Configuration

After importing a model, update your `.env` file:

```env
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=deepseek-coder-6.7b
```

## Testing Your Model

Test if everything is working:

```bash
python manage.py test_llm
```

This will:
1. Check Ollama connection
2. Test text generation
3. Test embeddings
4. Validate model performance

## Hardware Requirements

### Minimum (6.7B Q4_K_M models):
- **CPU**: 4 cores
- **RAM**: 8GB
- **Storage**: 10GB free

### Recommended (6.7B Q4_K_M models):
- **CPU**: 8 cores
- **RAM**: 16GB
- **Storage**: 20GB free

### For 13B models:
- **RAM**: 16GB minimum
- **Storage**: 20GB free

### For 33B models:
- **RAM**: 32GB minimum
- **Storage**: 40GB free

## GPU Acceleration (Optional)

If you have a compatible GPU, Ollama can use it automatically:

### NVIDIA GPU:
- Install CUDA toolkit
- Ollama will detect and use GPU automatically

### Apple Silicon (M1/M2/M3):
- Metal acceleration works out of the box
- No additional setup needed

## Troubleshooting

### Model Download Fails

**Error**: Connection timeout
```bash
# Increase timeout or use wget with retries
wget --timeout=300 --tries=3 <url>
```

**Error**: Disk space
```bash
# Check available space
df -h

# Clean up if needed
python manage.py manage_models --delete <old-model>
```

### Ollama Import Fails

**Error**: `ollama: command not found`
```bash
# Install Ollama first
# Visit: https://ollama.ai/download
```

**Error**: `Error: invalid model file`
```bash
# Check file integrity
md5sum models/gguf/model.gguf

# Re-download if corrupted
```

### Out of Memory

**Error**: Ollama crashes or model won't load

**Solution**:
1. Use smaller quantization (Q4_K_M instead of Q6_K)
2. Use smaller model (6.7B instead of 13B)
3. Close other applications
4. Increase swap space

## Model Performance Comparison

Based on trading analysis tasks:

| Model | Speed | Accuracy | Resource | Score |
|-------|-------|----------|----------|-------|
| DeepSeek 6.7B Q4_K_M | Fast | Good | Low | ⭐⭐⭐⭐⭐ |
| DeepSeek 33B Q4_K_M | Slow | Excellent | High | ⭐⭐⭐⭐ |
| Mistral 7B Q4_K_M | Very Fast | Good | Low | ⭐⭐⭐⭐ |
| Llama 2 13B Q4_K_M | Medium | Good | Medium | ⭐⭐⭐ |
| OpenHermes 7B Q4_K_M | Fast | Very Good | Low | ⭐⭐⭐⭐ |

## Best Practices

1. **Start Small**: Begin with DeepSeek 6.7B Q4_K_M
2. **Test First**: Always test before production use
3. **Monitor Resources**: Watch RAM usage during inference
4. **Keep Updated**: Check for new model versions regularly
5. **Backup Metadata**: Save `models/metadata.json` for tracking

## Integration with Trading System

Once your model is set up, it will be used for:

1. **News Analysis**:
   - Sentiment extraction
   - Key insights identification
   - Market impact assessment

2. **Trade Validation**:
   - LLM validates proposed trades
   - Analyzes market conditions
   - Identifies risks

3. **Investor Call Analysis**:
   - Summarizes earnings calls
   - Extracts financial metrics
   - Determines management tone

4. **RAG Queries**:
   - Answer questions about stocks
   - Provide context-aware responses
   - Synthesize information from multiple sources

## Next Steps

After setting up your model:

1. **Test the LLM system**:
   ```bash
   python manage.py test_llm
   ```

2. **Process some news**:
   ```bash
   python manage.py fetch_news --limit 10
   ```

3. **Try RAG queries**:
   ```python
   from apps.llm.services import ask_question

   success, answer, sources = ask_question("What is the sentiment on NIFTY?")
   print(answer)
   ```

4. **Validate a trade**:
   ```python
   from apps.llm.services import validate_trade

   result = validate_trade(symbol="RELIANCE", direction="LONG")
   ```

---

**Questions or Issues?**
- Check Ollama docs: https://ollama.ai/
- Check Hugging Face: https://huggingface.co/
- Review logs: `tail -f logs/django.log`
