import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import feedparser
import sqlite3
import apprise
import schedule
import time
import os
import json
import logging
import re
import sys
import hashlib
from datetime import datetime, timezone
from dateutil import parser
from logging.handlers import RotatingFileHandler
import requests
import json
from requests.exceptions import RequestException
import time
import hashlib
import signal
from volcenginesdkarkruntime import Ark

log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

file_handler = RotatingFileHandler(
    'app.log', maxBytes=1024*1024*1, backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.DEBUG)

log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
level = getattr(logging, log_level, logging.INFO)

logging.basicConfig(
    level=level,
    handlers=[console_handler, file_handler]
)

logging.info(f"日志级别设置为: {log_level}")
logger = logging.getLogger(__name__)

# ====== 配置部分 ======RSS
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
    
]

KEYWORDS_FILE = "keywords.txt"

# 新文章时间阈值（小时），默认为24小时
NEW_ITEM_THRESHOLD_HOURS = int(os.environ.get('NEW_ITEM_THRESHOLD_HOURS', '24'))

NOTIFIERS = [n for n in [os.environ.get('EMAIL_NOTIFIER', '').strip()] if n]

for notifier in NOTIFIERS:
    if notifier.startswith('mailto://') and 'http://' in notifier:
        logging.warning(f"可能的协议错误: {notifier} 应使用 smtp:// 而非 http://")


# ====== 豆包大模型配置 ======

DOUBAO_API_KEY = os.environ.get('DOUBAO_API_KEY', '')
DOUBAO_ENDPOINT = os.environ.get('DOUBAO_ENDPOINT', '')
DOUBAO_MODEL = os.environ.get('DOUBAO_MODEL', '') 

if not DOUBAO_API_KEY:
    logger.warning("未配置豆包大模型API密钥，将使用传统单篇发送模式")
    logger.warning("请设置环境变量 DOUBAO_API_KEY 以启用AI整合功能")


def load_keywords():
    try:
        with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning(f"关键词文件 {KEYWORDS_FILE} 未找到，使用默认关键词")
        return ["machine learning", "deep learning", "artificial intelligence"]


DB_PATH = os.environ.get('DB_PATH')
if not DB_PATH:
    if os.path.exists('/app'):
        DB_PATH = '/app/data/papers.db'
    else:
        DB_PATH = os.path.join(os.getcwd(), 'papers.db')
logger.info(f"数据库路径: {DB_PATH}")


db_dir = os.path.dirname(DB_PATH)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)
    logger.info(f"创建数据库目录: {db_dir}")


if db_dir:
    try:
        import stat
        os.chmod(db_dir, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        logger.info(f"已设置数据库目录权限: {db_dir}")
    except Exception as dir_perm_e:
        logger.warning(f"设置数据库目录权限失败: {str(dir_perm_e)}")
        try:
            os.chmod(db_dir, 0o755)  
            logger.info(f"已使用备用权限设置数据库目录: {db_dir}")
        except Exception as dir_perm_e2:
            logger.warning(f"备用目录权限设置也失败: {str(dir_perm_e2)}")


if not os.access(db_dir, os.W_OK):
    logger.error(f"数据库目录不可写: {db_dir}")
    logger.error("尝试修复目录权限...")
    try:
        os.chmod(db_dir, 0o777)  # 最宽松的权限设置
        logger.info(f"已使用最宽松权限设置目录: {db_dir}")
        if not os.access(db_dir, os.W_OK):
            raise PermissionError(f"即使设置最宽松权限后，目录仍不可写: {db_dir}")
    except Exception as final_perm_e:
        logger.error(f"最终权限修复失败: {str(final_perm_e)}")
        raise PermissionError(f"无法写入数据库目录: {db_dir}")


class DatabaseConnection:
    def __enter__(self):
        self.conn = sqlite3.connect(DB_PATH, timeout=30)
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA busy_timeout=5000;")
        except Exception:
            pass
        self.cursor = self.conn.cursor()
        return self.cursor
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
            logging.error(f"数据库错误: {exc_val}")
        else:
            self.conn.commit()
        self.conn.close()


logger.info(f"尝试连接数据库: {DB_PATH}")
max_retries = 5
retry_delay = 2  
retry_count = 0
success = False
while retry_count < max_retries and not success:
    try:
        with DatabaseConnection() as cursor:
            cursor.execute('''CREATE TABLE IF NOT EXISTS papers
                         (id TEXT PRIMARY KEY, title TEXT, link TEXT, published_time DATETIME, sent INTEGER DEFAULT 0, abstract TEXT)''')
            logger.info("数据库表结构初始化成功")
            if os.path.exists(DB_PATH):
                logger.info(f"数据库文件已成功创建: {DB_PATH}")
                logger.info(f"文件大小: {os.path.getsize(DB_PATH)} bytes")
                
                try:
                    import stat
                    os.chmod(DB_PATH, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                    logger.info(f"已设置数据库文件权限: {DB_PATH}")
                except Exception as perm_e:
                    logger.warning(f"设置数据库文件权限失败: {str(perm_e)}")
                    try:
                        os.chmod(DB_PATH, 0o666)  
                        logger.info(f"已使用备用权限设置数据库文件: {DB_PATH}")
                    except Exception as perm_e2:
                        logger.warning(f"备用权限设置也失败: {str(perm_e2)}")
            else:
                logger.error(f"数据库文件创建失败，路径: {DB_PATH}")
        success = True
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            retry_count += 1
            if retry_count >= max_retries:
                logger.error(f"数据库锁定错误，已达到最大重试次数 {max_retries}")
                raise
            logger.warning(f"数据库锁定，正在重试 ({retry_count}/{max_retries})...")
            time.sleep(retry_delay)
        else:
            logger.error(f"数据库操作错误: {str(e)}", exc_info=True)
            raise
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}", exc_info=True)
        raise
if not success:
    raise Exception("数据库初始化失败，已达到最大重试次数")


def get_feed_source(link):
    sources = {
        'export.arxiv.org': 'arXiv',
        'nature.com': 'Nature Machine Intelligence',
        'openai.com': 'OpenAI',
        'microsoft.com/en-us/research': 'Microsoft Research',
        'aws.amazon.com/blogs/machine-learning': 'AWS Machine Learning',
        'developer.nvidia.com': 'NVIDIA Developer'
    }
    for keyword, name in sources.items():
        if keyword in link.lower():
            return name
    return 'Other'


def update_article_sent_by_link(link, max_retries=5, retry_delay=0.5):
    for attempt in range(max_retries):
        try:
            with DatabaseConnection() as cursor:
                cursor.execute("UPDATE papers SET sent = 1 WHERE link = ?", (link,))
                rows_affected = cursor.rowcount
            if rows_affected and rows_affected > 0:
                logger.info(f"已更新文章发送状态: link={link} (影响行数: {rows_affected})")
                return True
            else:
                logger.warning(f"未找到匹配文章记录: link={link}")
                return False
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if ("database is locked" in msg or "locked" in msg) and attempt < max_retries - 1:
                logger.warning(f"数据库锁定，正在重试 ({attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
                continue
            logger.error(f"更新发送状态失败(不可恢复): {str(e)}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"更新发送状态失败: {str(e)}", exc_info=True)
            return False
    return False


def mark_all_unsent_as_sent(max_retries=5, retry_delay=0.5):
    for attempt in range(max_retries):
        try:
            with DatabaseConnection() as cursor:
                cursor.execute("UPDATE papers SET sent = 1 WHERE sent = 0")
                rows_affected = cursor.rowcount
            logger.info(f"批量更新发送状态完成，影响行数: {rows_affected}")
            return True
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if ("database is locked" in msg or "locked" in msg) and attempt < max_retries - 1:
                logger.warning(f"数据库锁定，正在重试 ({attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
                continue
            logger.error(f"批量更新发送状态失败(不可恢复): {str(e)}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"批量更新发送状态失败: {str(e)}", exc_info=True)
            return False
    return False

def send_email_notification(title: str, body: str) -> bool:
    if not NOTIFIERS:
        logger.warning("没有配置通知器，无法发送邮件通知")
        logger.warning("请检查环境变量 EMAIL_NOTIFIER 是否正确配置")
        return False

    max_tries = int(os.environ.get('MAIL_RETRY', '3'))
    backoff = float(os.environ.get('MAIL_RETRY_BACKOFF', '2'))  

    for attempt in range(1, max_tries + 1):
        apobj = apprise.Apprise()
        for n in NOTIFIERS:
            add_result = apobj.add(n)
            if not add_result:
                logger.error(f"添加通知器失败: {n}")
                logger.error("请检查邮件服务器配置是否正确")
                return False

        try:
            result = apobj.notify(body=body, title=title, body_format='markdown')
            if result:
                logger.info(f"邮件发送成功: {title}")
                return True
            else:
                logger.warning(f"邮件发送失败(返回 False): {title}")
                logger.warning("可能的原因: 1) SMTP服务器拒绝连接 2) 认证失败 3) 网络问题")
        except Exception as e:
            logger.error(f"邮件发送异常(第{attempt}次): {str(e)}", exc_info=True)
            if "authentication" in str(e).lower():
                logger.error("认证失败，请检查用户名和密码是否正确")
            elif "connection" in str(e).lower():
                logger.error("连接失败，请检查SMTP服务器地址和端口是否正确")
            elif "timeout" in str(e).lower():
                logger.error("连接超时，请检查网络连接")

        if attempt < max_tries:
            sleep_s = backoff ** (attempt - 1)
            logger.info(f"{title} 将在 {sleep_s}s 后重试发送 ({attempt+1}/{max_tries})")
            time.sleep(sleep_s)

    logger.error(f"邮件发送最终失败，已尝试 {max_tries} 次: {title}")
    return False

def call_doubao_llm(articles_data):
    if not DOUBAO_API_KEY:
        logger.warning("未配置豆包大模型API，跳过AI整合")
        return None, None
    
    try:
        articles_info = ""
        for i, article in enumerate(articles_data, 1):
            title, link, summary, published, source = article
            articles_info += f"{i}. 标题: {title}\n"
            articles_info += f"   来源: {source}\n"
            articles_info += f"   发布时间: {published}\n"
            articles_info += f"   完整摘要: {summary}\n"
            articles_info += f"   链接: {link}\n\n"
        
        system_prompt = """你是一个AI领域的专业分析师，擅长总结和分析AI相关的最新研究和技术动态。请根据提供的文章信息，完成以下任务：

1. 生成一个简洁有力的邮件标题，概括邮件内容中对ai领域最具影响力的内容，直接描述内容重点，不要包含"邮件标题"等字样
2. 将所有文章整合成一封结构清晰的邮件内容，必须包括：
   - 开头的问候语和本期概述
   - 逐一列出每篇文章的详细信息，包含：标题、来源、完整摘要、链接
   - 确保包含提供的所有文章，不能遗漏任何一篇
   - 结尾提供整体总结

格式要求：
- 第一行：直接写邮件标题（不要前缀"邮件标题："）
- 第二行：---分隔符---
- 第三行开始：邮件正文内容
- 每篇文章都要有完整的摘要信息
- 用中文回复，语言专业且易懂
- 对每篇文章内容的格式示例如下：
一、标题
1.摘要
2.链接
3.来源
二、...
""" 
        user_prompt = f"请分析以下{len(articles_data)}篇AI相关文章，并生成邮件标题和内容：\n\n{articles_info}"
        
        client = Ark(
            api_key=DOUBAO_API_KEY,
            base_url=DOUBAO_ENDPOINT
        )
        
        logger.info(f"正在调用豆包大模型整合{len(articles_data)}篇文章...")
        
        response = client.chat.completions.create(
            model=DOUBAO_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000
        )
        
        result = response.choices[0].message.content.strip()
        
        if "---" in result:
            parts = result.split("---", 1)
            email_title = parts[0].strip()
            email_body = parts[1].strip()
        else:
            email_title = f"AI领域最新动态汇总 - {len(articles_data)}篇重要文章"
            email_body = result
        
        logger.info(f"豆包大模型调用成功，生成标题: {email_title}")
        return email_title, email_body
        
    except Exception as e:
        logger.error(f"调用豆包大模型失败: {str(e)}", exc_info=True)
        return None, None

def call_doubao_llm_batch(articles_data, batch_num, total_batches):
    if not DOUBAO_API_KEY:
        logger.warning("未配置豆包大模型API，跳过AI整合")
        return None, None
    
    try:
        articles_info = ""
        for i, article in enumerate(articles_data, 1):
            title, link, summary, published, source = article
            articles_info += f"{i}. 标题: {title}\n"
            articles_info += f"   来源: {source}\n"
            articles_info += f"   发布时间: {published}\n"
            articles_info += f"   完整摘要: {summary}\n"
            articles_info += f"   链接: {link}\n\n"
        
        key_topics = []
        for article in articles_data:
            title, _, summary, _, _ = article
            text = f"{title} {summary}".lower()
            if any(keyword in text for keyword in ['gpt', 'llm', '大模型', 'transformer']):
                key_topics.append('大语言模型')
            elif any(keyword in text for keyword in ['computer vision', 'cv', '计算机视觉', 'image']):
                key_topics.append('计算机视觉')
            elif any(keyword in text for keyword in ['machine learning', 'ml', '机器学习']):
                key_topics.append('机器学习')
            elif any(keyword in text for keyword in ['deep learning', 'dl', '深度学习']):
                key_topics.append('深度学习')
            elif any(keyword in text for keyword in ['ai', 'artificial intelligence', '人工智能']):
                key_topics.append('人工智能')
        
        if key_topics:
            most_common = max(set(key_topics), key=key_topics.count)
            influence_desc = f"{most_common}重大突破"
        else:
            influence_desc = "前沿技术进展"
        
        system_prompt = f"""你是一个AI领域的专业分析师，擅长总结和分析AI相关的最新研究和技术动态。请根据提供的文章信息，完成以下任务：

1. 生成邮件标题，格式必须为："AI前沿：‘这些文章中最具影响力的更新内容’"，其中"最具影响力的更新内容"部分要根据文章内容具体描述，如"{influence_desc}"等
2. 将所有文章整合成一封结构清晰的邮件内容，必须包括：
   - 开头的问候语和本期概述（第{batch_num}批，共{total_batches}批）
   - 逐一列出每篇文章的详细信息，包含：标题、来源、完整摘要、链接
   - 确保包含提供的所有文章，不能遗漏任何一篇
   - 结尾提供整体总结，附上日期
   - 邮件内容总长度控制在4500字符以内

格式要求：
- 第一行：直接写邮件标题（不要前缀"邮件标题："）
- 第二行：---分隔符---
- 第三行开始：邮件正文内容
- 每篇文章都要有完整的摘要信息
- 用中文回复，语言专业严谨
- 对每篇文章内容的格式示例如下：
一、标题
1.摘要
2.链接
3.来源
二、...
""" 
        user_prompt = f"请分析以下第{batch_num}批（共{total_batches}批）的{len(articles_data)}篇AI相关文章，并生成邮件标题和内容：\n\n{articles_info}"
        
        client = Ark(
            api_key=DOUBAO_API_KEY,
            base_url=DOUBAO_ENDPOINT
        )
        
        logger.info(f"正在调用豆包大模型整合第{batch_num}批{len(articles_data)}篇文章...")
        
        response = client.chat.completions.create(
            model=DOUBAO_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=3500  
        )
        
        result = response.choices[0].message.content.strip()
        
        if "---" in result:
            parts = result.split("---", 1)
            email_title = parts[0].strip()
            email_body = parts[1].strip()
        else:
            email_title = f"AI前沿+{influence_desc}（第{batch_num}批）"
            email_body = result
        
        logger.info(f"豆包大模型调用成功，生成第{batch_num}批标题: {email_title}")
        return email_title, email_body
        
    except Exception as e:
        logger.error(f"调用豆包大模型失败: {str(e)}", exc_info=True)
        return None, None

def test_email_configuration():
    logger.info("开始测试邮件配置...")
    test_title = "邮件配置测试"
    test_body = "这是一封测试邮件，用于验证邮件推送系统配置是否正确。\n\n如果您收到这封邮件，说明配置成功！"
    
    success = send_email_notification(test_title, test_body)
    if success:
        logger.info("✅ 邮件配置测试成功！")
        return True
    else:
        logger.error("❌ 邮件配置测试失败，请检查配置")
        return False

def ai_integrated_batch_send():
    try:
        with DatabaseConnection() as cursor:
            cursor.execute("SELECT title, link, published_time, abstract FROM papers WHERE sent = 0")
            articles = cursor.fetchall()

        if not articles:
            logger.info("没有新文章需要发送")
            return

        logger.info(f"发现{len(articles)}篇未发送文章，准备分批AI整合")

        articles_data = []
        for title, link, published, abstract in articles:
            source = get_feed_source(link)
            summary = abstract if abstract else title  
            articles_data.append((title, link, summary, published, source))

        batch_size = 10
        total_batches = (len(articles_data) + batch_size - 1) // batch_size
        successful_batches = 0
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(articles_data))
            batch_articles = articles_data[start_idx:end_idx]
            
            logger.info(f"处理第{batch_num + 1}/{total_batches}批，包含{len(batch_articles)}篇文章")
            
            if DOUBAO_API_KEY:
                email_title, email_body = call_doubao_llm_batch(batch_articles, batch_num + 1, total_batches)
                
                if email_title and email_body:
                    logger.info(f"发送第{batch_num + 1}批AI整合邮件: {email_title}")
                    success = send_email_notification(email_title, email_body)
                else:
                    logger.warning(f"第{batch_num + 1}批AI整合失败，使用传统批量发送方式")
                    success = send_traditional_batch_limited(batch_articles, batch_num + 1, total_batches)
            else:
                logger.info(f"未配置AI模型，使用传统批量发送方式处理第{batch_num + 1}批")
                success = send_traditional_batch_limited(batch_articles, batch_num + 1, total_batches)

            if success:
                successful_batches += 1
                batch_links = [article[1] for article in batch_articles]  
                mark_batch_as_sent(batch_links)
                logger.info(f"第{batch_num + 1}批邮件发送成功")
            else:
                logger.warning(f"第{batch_num + 1}批邮件发送失败，保留 sent=0 以便下次重试")
            
            if batch_num < total_batches - 1:
                time.sleep(2)
        
        logger.info(f"批量发送完成：成功{successful_batches}/{total_batches}批，共处理{len(articles)}篇文章")
            
    except Exception as e:
        logger.error(f"AI整合批量发送失败: {str(e)}", exc_info=True)

def send_traditional_batch(articles):
    try:
        email_content = "# AI领域最新文章汇总\n\n"
        email_content += f"本期共收录 {len(articles)} 篇重要文章：\n\n"
        
        for i, (title, link, published) in enumerate(articles, 1):
            source = get_feed_source(link)
            email_content += f"## {i}. {title}\n"
            email_content += f"**来源**: {source}\n"
            email_content += f"**发布时间**: {published}\n"
            email_content += f"**链接**: [阅读全文]({link})\n\n"

        email_title = f"AI领域最新动态汇总 - {len(articles)}篇重要文章"
        return send_email_notification(email_title, email_content)
        
    except Exception as e:
        logger.error(f"传统批量发送失败: {str(e)}")
        return False

def send_traditional_batch_limited(articles_data, batch_num, total_batches):
    try:
        key_topics = []
        for article in articles_data:
            title, _, summary, _, _ = article
            text = f"{title} {summary}".lower()
            if any(keyword in text for keyword in ['gpt', 'llm', '大模型', 'transformer']):
                key_topics.append('大语言模型')
            elif any(keyword in text for keyword in ['computer vision', 'cv', '计算机视觉', 'image']):
                key_topics.append('计算机视觉')
            elif any(keyword in text for keyword in ['machine learning', 'ml', '机器学习']):
                key_topics.append('机器学习')
            elif any(keyword in text for keyword in ['deep learning', 'dl', '深度学习']):
                key_topics.append('深度学习')
            elif any(keyword in text for keyword in ['ai', 'artificial intelligence', '人工智能']):
                key_topics.append('人工智能')
        
        if key_topics:
            most_common = max(set(key_topics), key=key_topics.count)
            influence_desc = f"{most_common}重大突破"
        else:
            influence_desc = "前沿技术进展"
        
        email_title = f"AI前沿+{influence_desc}"
        if total_batches > 1:
            email_title += f"（第{batch_num}批）"
        
        email_content = f"# AI领域最新文章汇总（第{batch_num}批，共{total_batches}批）\n\n"
        email_content += f"本批次共收录 {len(articles_data)} 篇重要文章：\n\n"
        
        for i, (title, link, summary, published, source) in enumerate(articles_data, 1):
            email_content += f"## {i}. {title}\n"
            email_content += f"**来源**: {source}\n"
            email_content += f"**发布时间**: {published}\n"
            email_content += f"**摘要**: {summary}\n"
            email_content += f"**链接**: [阅读全文]({link})\n\n"
        
        if total_batches > 1:
            email_content += f"\n---\n本次为第{batch_num}批推送，共{total_batches}批。"
        
        return send_email_notification(email_title, email_content)
        
    except Exception as e:
        logger.error(f"传统批量发送失败: {str(e)}")
        return False

def mark_batch_as_sent(batch_links):
    try:
        with DatabaseConnection() as cursor:
            for link in batch_links:
                cursor.execute("UPDATE papers SET sent = 1 WHERE link = ?", (link,))
        logger.info(f"成功标记{len(batch_links)}篇文章为已发送")
    except Exception as e:
        logger.error(f"标记批次文章失败: {str(e)}", exc_info=True)

def summarize_and_send_batch():
    ai_integrated_batch_send()

def send_notification(entry):
    
    def timeout_handler(signum, frame):
        raise TimeoutError("邮件发送超时")
    
    try:
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(30)
        
        logger.info(f"开始构建邮件内容: {entry.title}")
        
        authors = getattr(entry, 'author', 'Unknown')
        published = getattr(entry, 'published', 'Unknown date')
        summary = getattr(entry, 'summary', 'No abstract available')
        source = get_feed_source(entry.link)

        title = f"新文章通知: {entry.title}"
        body = f"# {entry.title}\n\n"
        body += f"**来源**: {source}\n"
        body += f"**作者**: {authors}\n"
        body += f"**发布时间**: {published}\n\n"
        body += f"**摘要**: {summary}\n\n"
        body += f"[阅读全文]({entry.link})"
        
        logger.info(f"开始发送邮件: {entry.title}")

        ok = send_email_notification(title, body)
        if ok:
            logger.info(f"邮件发送成功，开始更新数据库状态: {entry.title}")
            update_article_sent_by_link(entry.link)
            return True
        else:
            logger.warning(f"文章通知发送失败: {entry.title}，不更新发送状态")
            return False
            
    except TimeoutError:
        logger.error(f"邮件发送超时: {entry.title}")
        return False
    except Exception as e:
        logger.error(f"发送通知时出错: {entry.title}, 错误详情: {str(e)}", exc_info=True)
        return False
    finally:
        signal.alarm(0)

def validate_rss_feeds(feeds, timeout=10, max_retries=2):
    valid_feeds = []
    
    for feed_url in feeds:
        if not feed_url or not feed_url.strip(): 
            continue
            
        for attempt in range(max_retries + 1):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                response = requests.get(
                    feed_url, 
                    timeout=timeout, 
                    allow_redirects=True, 
                    stream=True,
                    verify=False,  
                    headers=headers
                )
                
                if response.status_code < 400:
                    try:
                        feed = feedparser.parse(feed_url)
                        
                        if not hasattr(feed, 'bozo'):
                            logger.warning(f"RSS源解析异常，feedparser返回对象缺少bozo属性: `{feed_url}`")
                            break
                            
                        has_entries = hasattr(feed, 'entries') and len(feed.entries) > 0
                        has_feed_info = hasattr(feed, 'feed') and hasattr(feed.feed, 'title')
                        
                        if feed.bozo == 0 and (has_entries or has_feed_info):
                            valid_feeds.append(feed_url)
                            logger.info(f"RSS源验证通过: `{feed_url}`")
                            break
                        elif feed.bozo != 0:
                            # 安全地获取bozo_exception
                            bozo_error = getattr(feed, 'bozo_exception', '未知解析错误')
                            if attempt < max_retries:
                                logger.warning(f"RSS源解析错误，重试中 ({attempt + 1}/{max_retries + 1}): `{feed_url}` (错误: {bozo_error})")
                                time.sleep(1)  
                                continue
                            else:
                                logger.warning(f"RSS源内容无效: `{feed_url}` (错误: {bozo_error})")
                                break
                        else:
                            logger.warning(f"RSS源无内容或解析失败: `{feed_url}`")
                            break
                            
                    except Exception as parse_error:
                        if attempt < max_retries:
                            logger.warning(f"RSS解析异常，重试中 ({attempt + 1}/{max_retries + 1}): `{feed_url}` (错误: {str(parse_error)})")
                            time.sleep(1)
                            continue
                        else:
                            logger.error(f"RSS解析持续失败: `{feed_url}` (错误: {str(parse_error)})")
                            break
                else:
                    if attempt < max_retries:
                        logger.warning(f"RSS源请求失败，重试中 ({attempt + 1}/{max_retries + 1}): `{feed_url}` (状态码: {response.status_code})")
                        time.sleep(1)
                        continue
                    else:
                        logger.warning(f"RSS源请求失败: `{feed_url}` (状态码: {response.status_code})")
                        break
                        
            except requests.exceptions.SSLError as e:
                logger.warning(f"RSS源SSL错误，将跳过: `{feed_url}` (错误: {str(e)})")
                break
            except requests.exceptions.Timeout as e:
                if attempt < max_retries:
                    logger.warning(f"RSS源请求超时，重试中 ({attempt + 1}/{max_retries + 1}): `{feed_url}`")
                    time.sleep(2)
                    continue
                else:
                    logger.warning(f"RSS源请求超时，将跳过: `{feed_url}` (错误: {str(e)})")
                    break
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries:
                    logger.warning(f"RSS源连接错误，重试中 ({attempt + 1}/{max_retries + 1}): `{feed_url}`")
                    time.sleep(2)
                    continue
                else:
                    logger.warning(f"RSS源连接错误，将跳过: `{feed_url}` (错误: {str(e)})")
                    break
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"RSS源验证异常，重试中 ({attempt + 1}/{max_retries + 1}): `{feed_url}` (错误: {str(e)})")
                    time.sleep(1)
                    continue
                else:
                    logger.error(f"验证RSS源时出错: `{feed_url}` (错误: {str(e)})")
                    break
                    
    logger.info(f"RSS源验证完成，有效源数量: {len(valid_feeds)}/{len([f for f in feeds if f and f.strip()])}")
    return valid_feeds

# ====== 主任务 ======
def fetch_and_push():
    import time
    start_time = time.time()
    
    logger.info("开始执行RSS获取和推送任务")
    logger.info(f"任务开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    keywords = [k.lower() for k in load_keywords()]
    logger.info(f"Running fetch... keywords={keywords}")
    
    logger.info("开始验证RSS源...")
    valid_feeds = validate_rss_feeds(RSS_FEEDS)
    logger.info(f"已过滤无效RSS源，剩余: {len(valid_feeds)}/{len(RSS_FEEDS)}")
    if not valid_feeds:
        logger.error("所有RSS源均无效，请检查rsshub服务和网络连接")
    
    logger.info(f"开始处理 {len(valid_feeds)} 个有效的RSS源")
    
    total_articles = 0
    processed_articles = 0
    new_articles = 0
    
    for i, feed_url in enumerate(valid_feeds, 1):
        try:
            logger.info(f"正在解析RSS源 ({i}/{len(valid_feeds)}): {feed_url}")
            
            try:
                feed = feedparser.parse(feed_url)
            except Exception as parse_error:
                logger.error(f"feedparser解析失败: {feed_url}, 错误: {str(parse_error)}")
                continue
                
            if feed.bozo != 0:
                logger.warning(f"解析RSS失败: {feed_url}, 错误: {feed.bozo_exception}")
                continue
            
            entries = feed.entries
            total_articles += len(entries)
            logger.info(f"从 {feed_url} 获取到 {len(entries)} 篇文章")
            logger.info(f"进度: 已处理RSS源 {i}/{len(valid_feeds)}, 累计文章 {total_articles} 篇")
            
            for j, entry in enumerate(entries, 1):
                processed_articles += 1

                pattern = re.compile(r'\b(' + '|'.join(re.escape(k) for k in keywords) + r')\b', re.IGNORECASE)
                
                published_time = None
                if hasattr(entry, 'published'):
                    try:
                        published_time = parser.parse(entry.published)
                    except (ValueError, TypeError):
                        logger.warning(f"无法解析发布时间: {entry.published}")
                
                threshold_seconds = NEW_ITEM_THRESHOLD_HOURS * 3600
                try:
                    current_time = datetime.now(timezone.utc)
                    if published_time and published_time.tzinfo is None:
                        published_time = published_time.replace(tzinfo=timezone.utc)
                    if not published_time or (current_time - published_time).total_seconds() >= threshold_seconds:
                         continue
                except Exception as e:
                    logger.error(f"处理文章时间时出错: {str(e)}")
                    continue
                
                if 'title' in entry and pattern.search(entry.title):
                    logger.info(f"文章符合条件: {entry.title}")
                    try:
                        notify_after_insert = False
                        with DatabaseConnection() as cursor:
                            cursor.execute("SELECT id FROM papers WHERE link = ?", (entry.link,))
                            existing = cursor.fetchone()
                            if existing:
                                logger.info(f"文章已存在于数据库: {entry.title}")
                                continue
                            
                            logger.info(f"发现新文章，准备插入数据库: {entry.title}")

                            article_id = hashlib.md5(entry.link.encode()).hexdigest()
                            
                            abstract = getattr(entry, 'summary', '') or getattr(entry, 'description', '') or ''
                            if abstract:
                                abstract = re.sub(r'<[^>]+>', '', abstract)  
                                abstract = re.sub(r'\s+', ' ', abstract).strip()  

                            try:
                                logger.info(f"开始插入文章到数据库: {entry.title}")
                                cursor.execute(
                                    "INSERT INTO papers (id, title, link, published_time, abstract) VALUES (?, ?, ?, ?, ?)",
                                    (article_id, entry.title, entry.link, published_time.isoformat() if published_time else None, abstract)
                                )
                                logger.info(f"文章已成功存储到数据库: {entry.title}")
                                new_articles += 1
                                notify_after_insert = True
                            except sqlite3.IntegrityError:
                                logger.warning(f"文章已存在于数据库 (主键冲突): {entry.title}")
                            except Exception as e:
                                logger.error(f"插入文章到数据库失败: {str(e)}", exc_info=True)
                                raise
                        if notify_after_insert:
                            logger.info(f"新文章已存储，等待批量处理: {entry.title}")
                    except sqlite3.IntegrityError:
                        continue  
                    except Exception as e:
                        logger.error(f"处理文章时出错: {entry.title}, 错误: {str(e)}")
                else:
                    pass
        except Exception as e:
            logger.error(f"处理RSS源时出错: {feed_url}, 错误: {str(e)}")
            continue
    
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"RSS获取和推送任务完成")
    logger.info(f"任务结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"任务耗时: {duration:.2f}秒")
    logger.info(f"处理统计: 总文章数 {total_articles}, 新文章数 {new_articles}, 处理文章数 {processed_articles}")



if __name__ == "__main__":
    print("=== 应用程序启动 ===")
    print("开始初始化日志系统...")
    required_files = [KEYWORDS_FILE]
    for file in required_files:
        if not os.path.exists(file):
            print(f"警告: 必要文件不存在 - {file}")
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        print(f"警告: 数据库目录不存在 - {db_dir}")
        os.makedirs(db_dir, exist_ok=True)
        print(f"已自动创建数据库目录 - {db_dir}")
        
        try:
            import stat
            os.chmod(db_dir, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
            print(f"已设置数据库目录权限: {db_dir}")
        except Exception as dir_perm_e:
            print(f"设置数据库目录权限失败: {str(dir_perm_e)}")
            try:
                os.chmod(db_dir, 0o755)  # 备用权限设置
                print(f"已使用备用权限设置数据库目录: {db_dir}")
            except Exception as dir_perm_e2:
                print(f"备用目录权限设置也失败: {str(dir_perm_e2)}")
    print("初始化检查完成")
    print(f"环境变量 LOG_LEVEL: {os.environ.get('LOG_LEVEL')}")
    print(f"通知器配置: {NOTIFIERS}")
    print(f"数据库路径: {DB_PATH}")

    print(f"RSS源数量: {len(RSS_FEEDS)}")
    
    if NOTIFIERS:
        test_email_configuration()
    
    try:
        notification_freq = os.environ.get('NOTIFICATION_FREQUENCY', 'hourly').lower()
        logger.info(f"配置的通知频率: {notification_freq}")
        
        if notification_freq == 'daily':
            schedule.every(1).days.do(summarize_and_send_batch)
            logger.info("已安排每日批量发送任务")
        elif notification_freq == 'weekly':
            schedule.every(1).weeks.do(summarize_and_send_batch)
            logger.info("已安排每周批量发送任务")
        else:  # 默认每小时
            schedule.every(1).hours.do(summarize_and_send_batch)
            logger.info("已安排每小时批量发送任务")
        
        schedule.every(1).hours.do(fetch_and_push)
        logger.info("已安排每小时RSS抓取任务")
        
        logger.info(f"当前已安排的定时任务数量: {len(schedule.jobs)}")
        for job in schedule.jobs:
            logger.info(f"任务: {job.job_func.__name__}, 下次运行时间: {job.next_run}")
        
        fetch_and_push()  
        
        logger.info("启动时立即执行一次批量发送任务")
        summarize_and_send_batch()
        
        logger.info("进入定时任务循环...")
        loop_count = 0
        last_job_check = 0
        while True:
            pending_jobs = [job for job in schedule.jobs if job.should_run]
            if pending_jobs:
                logger.info(f"发现 {len(pending_jobs)} 个待执行任务")
                for job in pending_jobs:
                    logger.info(f"执行任务: {job.job_func.__name__}")
            
            schedule.run_pending()
            time.sleep(10)
            loop_count += 1
                     

    except Exception as e:
        print(f"程序执行失败: {str(e)}")
        raise
