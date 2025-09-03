# 🚀 AI Paper & Article Push System

An AI-powered intelligent paper and article push system that automatically fetches multiple academic RSS sources, utilizes Doubao LLM for intelligent summarization and title generation, supports smart batch sending and automatic fallback mechanisms, and delivers content to users via email.

## 📋 Project Overview

This system aims to help researchers and scholars stay up-to-date with the latest academic paper information. Through keyword filtering, AI intelligent summarization, and batch processing, users can quickly understand the latest research developments in relevant fields. The system features high reliability, supporting intelligent fallback when AI services are unavailable, ensuring continuity of email delivery.

### 🎯 Core Features

- **🤖 AI Smart Integration**: Integrates Doubao LLM for intelligent summarization and integration of multiple articles
- **📡 Multi-source RSS Fetching**: Supports multiple authoritative academic sources like arXiv, Nature, OpenAI, etc.
- **🔍 Smart Keyword Filtering**: Precise article filtering based on custom keyword library
- **📧 Smart Batch Delivery**: Maximum 10 articles per email, automatic batch sending for excess
- **🎯 Smart Title Generation**: AI automatically extracts the most impactful content to generate email titles
- **💾 Data Persistence**: SQLite database storage, avoiding duplicate pushes, supports automatic permission repair
- **🐳 Containerized Deployment**: Complete Docker deployment solution, including RSSHub service
- **⏰ Flexible Scheduling**: Supports multiple push frequencies like hourly/daily/weekly
- **📊 Comprehensive Logging**: Detailed runtime logs and error handling mechanisms
- **🔄 Smart Fallback**: Automatically switches to traditional push mode when AI services are unavailable

### 🏗️ System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   RSS Sources   │──▶│  Article Filter  │──▶│   Batch Logic   │
│ (arXiv, Nature, │    │   (Keywords)     │    │ (Max 10/batch)  │
│     OpenAI...)  │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AI Summary    │◀──│  Smart Routing   │──▶│ Traditional     │
│  (Doubao LLM)   │    │   (Fallback)     │    │ Summary Mode    │
│                 │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Email Notify   │◀──│   SQLite DB      │──▶│  Data Storage   │
│ (Batch Send)    │    │ (Deduplication)  │    │   (Articles)    │
│                 │    │ (Auto Repair)    │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 📦 Quick Start

### Method 1: Docker Deployment (Recommended)

1. **Clone the Project**
   ```bash
   git clone https://github.com/qfbase/AIPaperPush
   cd AIPaperPush
   ```

2. **Configure Environment Variables**
   ```bash
   cp .env.example .env
   # Edit .env file to configure email and API keys
   ```

3. **Start Services**
   ```bash
   docker-compose up -d
   ```

4. **View Logs**
   ```bash
   docker-compose logs -f ai_paper_push
   ```

### Method 2: Local Execution

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   ```bash
   # Create .env file and configure necessary parameters
   # Ensure keywords.txt file exists
   ```

3. **Run Program**
   ```bash
   python fetch_and_push.py
   ```

## ⚙️ Configuration Guide

### Environment Variables Configuration (.env)

```bash
# Email notifier configuration
# Format: mailto://username:password@SMTP_server
EMAIL_NOTIFIER=mailto://your_email:your_password@smtp.163.com

# Notification frequency configuration
# Options: hourly, daily, weekly
NOTIFICATION_FREQUENCY=daily

# Article filtering configuration
# Only push new articles within specified hours, default 24 hours
NEW_ITEM_THRESHOLD_HOURS=24

# Doubao LLM API configuration
# Get from: https://console.volcengine.com/ark
DOUBAO_API_KEY=your_doubao_api_key_here
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=your_model_id_here

# System configuration
# Log levels: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Docker deployment related configuration
# Database path (Docker container internal path)
DB_PATH=/app/data/papers.db

# Keywords file path (Docker container internal path)
KEYWORDS_FILE=/app/keywords.txt

# Python buffer configuration (Docker recommended setting)
PYTHONUNBUFFERED=1

# RSS source configuration (optional)
# To override default RSS sources, set this variable
# RSS_FEEDS_OVERRIDE=https://example.com/rss1,https://example.com/rss2
```

### Keywords Configuration (keywords.txt)

Configure keywords of interest in the `keywords.txt` file, one per line:

```
LLM
Transformer
Diffusion
Reinforcement Learning
Neural Networks
Deep Learning
GPT
BERT
...
```

### RSS Source Configuration

The system includes the following RSS sources by default:
- arXiv AI/ML/CV/CL categories
- Nature Machine Intelligence
- OpenAI Blog
- Microsoft Research
- AWS Machine Learning Blog
- NVIDIA Developer Blog

#### Custom RSS Sources

You can add or remove RSS sources by modifying the `RSS_FEEDS` list in the `fetch_and_push.py` file:

```python
RSS_FEEDS = [
    "https://export.arxiv.org/rss/cs.AI",
    "https://export.arxiv.org/rss/cs.LG", 
    "https://export.arxiv.org/rss/cs.CV",
    "https://export.arxiv.org/rss/cs.CL",
    "https://www.nature.com/natmachintell.rss",
    "https://openai.com/blog/rss.xml",
    "https://www.microsoft.com/en-us/research/feed/",
    "https://aws.amazon.com/blogs/machine-learning/feed/",
    "https://developer.nvidia.com/blog/feed/",
    # You can add more RSS sources here
    # "https://example.com/rss.xml",
]
```

**Notes:**
- Supports any standard RSS/Atom format sources
- Recommend adding academic and technical RSS sources
- Service restart required after adding new RSS sources
- System automatically validates RSS source availability

#### RSS Source Mapping Configuration

The system automatically identifies article sources through the `get_feed_source()` function. You can update mapping relationships based on newly added RSS sources:

```python
def get_feed_source(link):
    sources = {
        'arxiv': 'arXiv',
        'nature': 'Nature Machine Intelligence',
        'openai': 'OpenAI',
        'microsoft': 'Microsoft Research',
        'aws': 'AWS Machine Learning',
        'nvidia': 'NVIDIA Developer',
        # When adding new RSS sources, please add corresponding mapping here
        # 'example.com': 'Example Source Name'
    }
    for keyword, name in sources.items():
        if keyword in link.lower():
            return name
    return 'Other'
```

**Configuration Instructions:**
- `keyword`: Characteristic keyword in RSS source URL (recommend using domain name)
- `name`: Source name displayed in emails
- System matches in order, recommend placing more specific keywords first
- Unmatched sources will display as 'Other'

## 📊 Feature Details

### 1. RSS Source Fetching
- Scheduled fetching of configured RSS sources (arXiv, Nature, OpenAI, etc.)
- Automatic RSS source availability validation with retry mechanism
- SSL error handling and User-Agent configuration support
- Integrated RSSHub service for extended RSS source support

### 2. Smart Filtering
- Article title and abstract matching based on keywords
- Time threshold filtering, only pushing latest articles
- Database deduplication to avoid duplicate pushes
- Support for dynamic custom keyword library updates

### 3. Smart Batch Processing
- **Maximum 10 articles per email**, automatic batch sending for excess
- Automatic delays between batches to avoid email server limits
- Batch marking of sent status to ensure data consistency
- Batch information display support for easy tracking

### 4. AI Smart Integration
- Utilizes Doubao LLM for multi-article summarization
- **Smart extraction of most impactful content for email title generation**
- Automatic article topic identification (Large Language Models, Computer Vision, etc.)
- Generates structured push content with complete summaries and links

### 5. Smart Fallback Mechanism
- Automatically switches to traditional push mode when AI services are unavailable
- Traditional mode supports keyword matching for topic title generation
- Ensures high reliability of email delivery
- Seamless switching, transparent to users

### 6. Email Delivery
- Supports multiple SMTP services (163, Gmail, QQ, etc.)
- Smart batch delivery, maximum 10 articles per batch
- Rich email format with article details and source information
- Email sending retry and error handling support

## 🔧 Operations Management

### Log Management
- Application logs: `app.log` (rotated storage)
- Docker logs: `docker-compose logs`
- Log levels adjustable via environment variables

### Database Management
- SQLite database file: `papers.db`
- Contains article information, sending status, etc.
- Supports data persistence and backup

### Health Checks
- Docker container health checks
- Database connection status monitoring
- RSS source availability verification

## 🚨 Troubleshooting

### Common Issues

1. **Email Sending Failure**
   - Check SMTP configuration and password
   - Confirm third-party application authorization from email provider
   - Verify email server address and port
   - Check network connection and firewall settings

2. **RSS Source Parsing Failure**
   - Check network connection
   - Verify RSS source URL validity
   - Check SSL certificate issues
   - Confirm RSSHub service is running normally

3. **Doubao API Call Failure**
   - Verify API key and model ID
   - Check API quota and limits
   - Confirm network connection to Volcano Engine services
   - System will automatically fallback to traditional mode

4. **Database Permission Issues**
   - System automatically repairs database file permissions
   - Check disk space and directory permissions
   - Confirm Docker container user permission settings
   - Check if database directory is writable

5. **Database Locking**
   - System automatic retry mechanism (up to 5 times)
   - Enable WAL mode to reduce lock conflicts
   - Check disk space and I/O performance

6. **Batch Sending Issues**
   - Each email automatically limited to 10 articles
   - 2-second delay between batches to avoid limits
   - Check email provider's sending frequency limits

### Debug Mode

```bash
# Set debug log level
LOG_LEVEL=DEBUG

# View detailed logs
docker-compose logs -f ai_paper_push
```

## 📄 License

This project is licensed under the MIT License.
