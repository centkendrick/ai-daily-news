import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import feedparser
from datetime import datetime
from openai import OpenAI

# 强制标准输出无缓冲，让 GitHub Actions 实时显示 print 内容
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

# 从环境变量中读取配置
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_AUTH_CODE = os.getenv("SENDER_AUTH_CODE")
RECEIVER_EMAIL = "582141970@qq.com"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

def main():
    print("========== 任务开始 ==========", flush=True)
    
    # 1. 检查密钥是否存在
    if not DEEPSEEK_API_KEY:
        print("❌ 错误：未找到 DEEPSEEK_API_KEY 环境变量，请检查 Secrets 配置！", flush=True)
        return
    if not SENDER_EMAIL or not SENDER_AUTH_CODE:
        print("❌ 错误：未找到发件箱配置，请检查 SENDER_EMAIL 和 SENDER_AUTH_CODE！", flush=True)
        return
    
    print(f"✅ 环境变量读取成功，收件人：{RECEIVER_EMAIL}", flush=True)

    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com"
    )

    print("📡 正在抓取全球科技新闻...", flush=True)
    rss_urls = [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://www.wired.com/feed/rss",
        "https://www.jiqizhixin.com/rss"
    ]
    
    all_entries = []
    for url in rss_urls:
        try:
            print(f"-> 正在请求: {url}", flush=True)
            feed = feedparser.parse(url)
            print(f"   ✅ 成功获取 {len(feed.entries)} 条", flush=True)
            all_entries.extend(feed.entries[:5])
        except Exception as e:
            print(f"   ❌ 抓取失败: {e}", flush=True)
            
    if not all_entries:
        print("⚠️ 未抓取到任何新闻，任务终止。", flush=True)
        return

    print("🧠 正在调用 DeepSeek-Reasoner 进行深度推演...", flush=True)
    news_text = ""
    for i, entry in enumerate(all_entries[:12]):
        title = entry.title
        summary = entry.get('summary', '')[:200].replace('\n', ' ')
        news_text += f"【新闻{i+1}】\n标题：{title}\n摘要：{summary}\n---\n"

    prompt = f"""
    【角色】：你是一位顶级的全球科技与商业分析师。
    【任务】：请阅读以下最新抓取的全球科技新闻（中英文混合），提炼出 4-5 条最有价值的核心动向。
    【分析要求】：
    1. **事件核心（中英对照）**：用中文简述事件，并保留关键英文专业词汇或原文摘要。
    2. **商业化机会**：这给创业者、投资人或企业带来了什么赚钱/降本的机会？请给出具体场景。
    3. **潜在风险**：这件事可能带来什么政策、安全、伦理或商业上的风险？
    
    【新闻数据】：
    {news_text}
    
    【输出格式要求】：
    请直接输出排版精美的 HTML 内容（千万不要输出 ```html 等 Markdown 标记，只输出纯 HTML 标签），以便直接渲染到邮件里。
    请严格使用以下结构：
    <h3 style="color: #2c3e50;">1. [动向标题]</h3>
    <ul>
        <li><strong>事件核心：</strong>...</li>
        <li><strong>商业化机会：</strong><span style="color: green;">...</span></li>
        <li><strong>潜在风险：</strong><span style="color: red;">...</span></li>
    </ul>
    """
    
    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner", 
            messages=[{"role": "user", "content": prompt}]
        )
        html_content = response.choices[0].message.content
        print("✅ AI 深度分析完成！", flush=True)
    except Exception as e:
        print(f"❌ 调用 AI 失败: {e}", flush=True)
        return

    print(f"✉️ 正在发送邮件到 {RECEIVER_EMAIL}...", flush=True)
    
    final_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2 style="color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 10px;">
            🌍 全球 AI 动向与商业情报日报 ({datetime.now().strftime("%Y-%m-%d")})
        </h2>
        <p>你好！这是为你自动生成的今日 AI 圈深度分析报告。</p>
        <hr>
        {html_content}
        <hr>
        <p style="font-size: 12px; color: #888;">由 DeepSeek-Reasoner 与 GitHub Actions 自动驱动。</p>
    </body>
    </html>
    """
    
    mail_msg = MIMEText(final_html, 'html', 'utf-8')
    mail_msg['Subject'] = Header(f'【AI 日报】{datetime.now().strftime("%Y-%m-%d")} 全球动向与商业分析', 'utf-8')
    mail_msg['From'] = SENDER_EMAIL
    mail_msg['To'] = RECEIVER_EMAIL

    try:
        server = smtplib.SMTP_SSL("smtp.qq.com", 465)
        server.login(SENDER_EMAIL, SENDER_AUTH_CODE)
        server.sendmail(SENDER_EMAIL, [RECEIVER_EMAIL], mail_msg.as_string())
        server.quit()
        print("✅ 邮件发送成功！", flush=True)
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as global_e:
        print(f"💥 发生全局未捕获异常: {global_e}", flush=True)
    print("========== 任务结束 ==========", flush=True)
