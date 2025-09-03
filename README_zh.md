# 🚀 AI论文、文章推送系统

一个基于AI的智能论文、文章推送系统，自动抓取多种学术RSS源，利用豆包大模型进行智能摘要和标题生成，支持智能分批发送和自动回退机制，通过邮件推送给用户。

## 📋 项目概况

本系统旨在帮助研究人员和学者及时获取最新的学术论文信息。通过关键词过滤、AI智能摘要和分批处理，用户可以快速了解相关领域的最新研究进展。系统具备高可靠性，支持AI服务不可用时的智能回退，确保邮件推送的连续性。

### 🎯 核心特性

- **🤖 AI智能整合**: 集成豆包大模型，对多篇文章进行智能摘要和整合
- **📡 多源RSS抓取**: 支持arXiv、Nature、OpenAI等多个权威学术源
- **🔍 智能关键词过滤**: 基于自定义关键词库进行精准文章筛选
- **📧 智能分批推送**: 每封邮件最多包含10篇文章，超出自动分批发送
- **🎯 智能标题生成**: AI自动提取最具影响力的内容生成邮件标题
- **💾 数据持久化**: SQLite数据库存储，避免重复推送，支持权限自动修复
- **🐳 容器化部署**: 完整的Docker部署方案，包含RSSHub服务
- **⏰ 灵活调度**: 支持每小时/每日/每周等多种推送频率
- **📊 完善日志**: 详细的运行日志和错误处理机制
- **🔄 智能回退**: AI服务不可用时自动切换到传统推送模式

### 🏗️ 系统架构

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

## 📦 快速开始

### 方式一：Docker部署（推荐）

1. **克隆项目**
   ```bash
   git clone https://github.com/qfbase/AIPaperPush/tree/main
   cd AIPaperPush
   ```

2. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑.env文件，配置邮件和API密钥
   ```

3. **启动服务**
   ```bash
   docker-compose up -d
   ```

4. **查看日志**
   ```bash
   docker-compose logs -f ai_paper_push
   ```

### 方式二：本地运行

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **配置环境**
   ```bash
   # 创建.env文件并配置必要参数
   # 确保keywords.txt文件存在
   ```

3. **运行程序**
   ```bash
   python fetch_and_push.py
   ```

## ⚙️ 配置说明

### 环境变量配置 (.env)

```bash
# 邮件通知器配置
# 格式: mailto://用户名:密码@SMTP服务器
EMAIL_NOTIFIER=mailto://your_email:your_password@smtp.163.com

# 通知频率配置
# 可选值: hourly(每小时), daily(每日), weekly(每周)
NOTIFICATION_FREQUENCY=daily

# 文章筛选配置
# 只推送指定时间内的新文章，默认24小时
NEW_ITEM_THRESHOLD_HOURS=24

# 豆包大模型API配置
# 获取方式: https://console.volcengine.com/ark
DOUBAO_API_KEY=your_doubao_api_key_here
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_MODEL=your_model_id_here

# 系统配置
# 日志级别: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO

# Docker部署相关配置
# 数据库路径（Docker容器内路径）
DB_PATH=/app/data/papers.db

# 关键词文件路径（Docker容器内路径）
KEYWORDS_FILE=/app/keywords.txt

# Python缓冲区配置（Docker推荐设置）
PYTHONUNBUFFERED=1

# RSS源配置（可选）
# 如需覆盖默认RSS源，可以设置此变量
# RSS_FEEDS_OVERRIDE=https://example.com/rss1,https://example.com/rss2
```

### 关键词配置 (keywords.txt)

在`keywords.txt`文件中配置感兴趣的关键词，每行一个：

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

### RSS源配置

系统默认包含以下RSS源：
- arXiv AI/ML/CV/CL分类
- Nature Machine Intelligence
- OpenAI Blog
- Microsoft Research
- AWS Machine Learning Blog
- NVIDIA Developer Blog

#### 自定义RSS源

您可以通过修改 `fetch_and_push.py` 文件中的 `RSS_FEEDS` 列表来添加或删除RSS源：

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
    # 您可以在此添加更多RSS源
    # "https://example.com/rss.xml",
]
```

**注意事项：**
- 支持任何标准的RSS/Atom格式的源
- 建议添加学术性、技术性的RSS源
- 新增RSS源后需要重启服务生效
- 系统会自动验证RSS源的可用性

#### RSS来源映射配置

系统通过 `get_feed_source()` 函数自动识别文章来源，您可以根据新增的RSS源更新映射关系：

```python
def get_feed_source(link):
    sources = {
        'arxiv': 'arXiv',
        'nature': 'Nature Machine Intelligence',
        'openai': 'OpenAI',
        'microsoft': 'Microsoft Research',
        'aws': 'AWS Machine Learning',
        'nvidia': 'NVIDIA Developer',
        # 添加新RSS源时，请在此添加对应的映射关系
        # 'example.com': 'Example Source Name'
    }
```

## 📊 功能详解

### 1. RSS源抓取
- 定时抓取配置的RSS源（arXiv、Nature、OpenAI等）
- 自动验证RSS源可用性，支持重试机制
- 支持SSL错误处理和User-Agent设置
- 集成RSSHub服务，扩展RSS源支持

### 2. 智能过滤
- 基于关键词进行文章标题和摘要匹配
- 时间阈值过滤，只推送最新文章
- 数据库去重，避免重复推送
- 支持自定义关键词库动态更新

### 3. 智能分批处理
- **每封邮件最多包含10篇文章**，超出自动分批发送
- 批次间自动延迟，避免邮件服务器限制
- 分批标记已发送状态，确保数据一致性
- 支持批次信息显示，便于跟踪

### 4. AI智能整合
- 利用豆包大模型对多篇文章进行摘要
- **智能提取最具影响力的内容生成邮件标题**
- 自动识别文章主题（大语言模型、计算机视觉等）
- 生成结构化的推送内容，包含完整摘要和链接

### 5. 智能回退机制
- AI服务不可用时自动切换到传统推送模式
- 传统模式支持关键词匹配生成主题标题
- 确保邮件推送的高可靠性
- 无缝切换，用户无感知

### 6. 邮件推送
- 支持多种SMTP服务（163、Gmail、QQ等）
- 智能分批推送，每批最多10篇文章
- 丰富的邮件格式，包含文章详情和来源信息
- 支持邮件发送重试和错误处理

## 🔧 运维管理

### 日志管理
- 应用日志：`app.log`（轮转保存）
- Docker日志：`docker-compose logs`
- 日志级别可通过环境变量调整

### 数据库管理
- SQLite数据库文件：`papers.db`
- 包含文章信息、发送状态等
- 支持数据持久化和备份

### 健康检查
- Docker容器健康检查
- 数据库连接状态监控
- RSS源可用性验证

## 🚨 故障排除

### 常见问题

1. **邮件发送失败**
   - 检查SMTP配置和密码
   - 确认邮箱服务商的第三方应用授权
   - 验证邮件服务器地址和端口
   - 检查网络连接和防火墙设置

2. **RSS源解析失败**
   - 检查网络连接
   - 验证RSS源URL有效性
   - 查看SSL证书问题
   - 确认RSSHub服务是否正常运行

3. **豆包API调用失败**
   - 验证API密钥和模型ID
   - 检查API配额和限制
   - 确认网络连接到火山引擎服务
   - 系统会自动回退到传统模式

4. **数据库权限问题**
   - 系统会自动修复数据库文件权限
   - 检查磁盘空间和目录权限
   - 确认Docker容器的用户权限设置
   - 查看数据库目录是否可写

5. **数据库锁定**
   - 系统自动重试机制（最多5次）
   - 启用WAL模式减少锁冲突
   - 检查磁盘空间和I/O性能

6. **分批发送问题**
   - 每封邮件自动限制为10篇文章
   - 批次间有2秒延迟避免限制
   - 检查邮件服务商的发送频率限制

### 调试模式

```bash
# 设置调试日志级别
LOG_LEVEL=DEBUG

# 查看详细日志
docker-compose logs -f ai_paper_push
```


## 📄 许可证

本项目采用MIT许可证。

