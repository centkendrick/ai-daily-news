import os
import sys
import smtplib
import re
import feedparser
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制标准输出无缓冲
sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

# 从环境变量中读取配置
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_AUTH_CODE = os.getenv("SENDER_AUTH_CODE")
RECEIVER_EMAIL = "582141970@qq.com"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# 扩充的顶级 AI 资讯源
RSS_URLS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.jiqizhixin.com/rss",
    "https://www.technologyreview.com/topic/artificial-intelligence/feed",
    "https://www.wired.com/feed/tag/ai/latest/rss",
    "https://syncedreview.com/feed/",
    "https://www.marktechpost.com/feed/",
    "https://news.mit.edu/rss/topic/artificial-intelligence2",
    "https://openai.com/news/rss.xml",
    "https://www.artificialintelligence-news.com/feed/"
]

AI_KEYWORDS = ["AI", "人工智能", "大模型", "LLM", "算法", "算力", "模型", "深度学习", "AIGC", "OpenAI", "DeepSeek", "Anthropic", "Gemini", "Claude", "ChatGPT", "AGI"]

def clean_html(raw_html):
    """清理摘要中的 HTML 标签"""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.strip()

def fetch_and_filter_news():
    print("📡 开始抓取全球数十个 AI 媒体源...", flush=True)
    all_news = []
    seen_titles = set()

    for url in RSS_URLS:
        try:
            feed = feedparser.parse(url)
            source_name = feed.feed.get('title', url.split("//")[1].split("/")[0])
            for entry in feed.entries:
                title = entry.title
                if title in seen_titles: continue
                
                raw_summary = entry.get('summary', '')
                summary = clean_html(raw_summary)[:250]
                full_text = title + summary
                link = entry.get('link', '#')
                
                # 过滤非 AI 新闻
                if any(keyword in full_text for keyword in AI_KEYWORDS):
                    all_news.append({
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "source": source_name
                    })
                    seen_titles.add(title)
        except Exception as e:
            print(f"❌ 抓取失败 {url}: {e}", flush=True)

    print(f"✅ 成功获取并去重，共筛选出 {len(all_news)} 条纯 AI 新闻。", flush=True)
    return all_news

def analyze_batch(batch, batch_index):
    """处理一批新闻（每批5条），调用 Reasoner"""
    if not batch: return ""
    
    news_text = ""
    for i, n in enumerate(batch):
        news_text += f"【新闻{i+1}】\n标题：{n['title']}\n摘要：{n['summary']}\n---\n"

    prompt = f"""
    【角色】：你是一位顶级的全球科技与商业分析师。
    【任务】：请阅读以下 {len(batch)} 条新闻，提炼出最有价值的动向。如果不包含真正的 AI 核心进展，请直接跳过。
    【分析要求】：针对每条有价值的新闻，输出：
    1. **事件核心**：请直接用纯中文简述事件，不要包含英文原文。
    2. **商业化机会**：给创业者或企业带来什么赚钱/降本机会？请给具体场景。
    3. **潜在风险**：政策、安全、伦理或商业风险。

    【新闻数据】：
    {news_text}

    【输出格式】：严格输出 HTML，不要 Markdown 标记。
    <div class="news-card">
        <h3>[动向标题]</h3>
        <p><strong>事件核心：</strong>...</p>
        <p class="opportunity"><strong>💰 商业化机会：</strong>...</p>
        <p class="risk"><strong>⚠️ 潜在风险：</strong>...</p>
    </div>
    """
    
    try:
        print(f"🧠 正在请求大模型分析第 {batch_index + 1} 组新闻...", flush=True)
        response = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[{"role": "user", "content": prompt}]
        )
        html_content = response.choices[0].message.content
        return html_content.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        print(f"❌ 第 {batch_index + 1} 组分析失败: {e}", flush=True)
        return ""

def main():
    print("========== 任务开始 ==========", flush=True)
    
    if not DEEPSEEK_API_KEY or not SENDER_EMAIL:
        print("❌ 错误：环境变量未配置！", flush=True)
        return

    news_list = fetch_and_filter_news()
    if not news_list:
        return

    # 将新闻分组，每 5 条一组，避免大模型过载
    batch_size = 5
    batches = [news_list[i:i + batch_size] for i in range(0, len(news_list), batch_size)]

    # 使用多线程并发请求，加快处理几十条新闻的速度
    analyzed_html_blocks = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(analyze_batch, batch, idx): idx for idx, batch in enumerate(batches)}
        for future in as_completed(futures):
            result = future.result()
            if result:
                analyzed_html_blocks.append(result)

    if not analyzed_html_blocks:
        print("⚠️ 所有 AI 分析均失败，任务终止。", flush=True)
        return

    # 拼接所有分析好的新闻卡片
    final_news_html = "\n".join(analyzed_html_blocks)
    
    # 构建新闻来源和原文链接的补充信息
    source_links_html = "<h3 style='color:#2c3e50; border-bottom:1px solid #ccc; padding-bottom:10px;'>🔗 原文与来源汇总</h3><ul>"
    for n in news_list:
        source_links_html += f"<li><strong>{n['source']}</strong> - <a href='{n['link']}' style='color:#3498db; text-decoration:none;'>{n['title']}</a></li>"
    source_links_html += "</ul>"

    # 终极 HTML 模板
    final_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background-color: #f4f7f6; color: #333; line-height: 1.6; margin: 0; padding: 20px; }}
            .container {{ max-width: 750px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 30px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); }}
            .header {{ text-align: center; border-bottom: 2px solid #eaeaea; padding-bottom: 20px; margin-bottom: 30px; }}
            .header h1 {{ color: #2c3e50; margin: 0; font-size: 26px; }}
            .news-card {{ background: #f9fbfc; border-left: 4px solid #3498db; border-radius: 6px; padding: 20px; margin-bottom: 25px; box-shadow: 0 2px 5px rgba(0,0,0,0.02); }}
            .news-card h3 {{ margin-top: 0; color: #2980b9; font-size: 18px; }}
            .news-card p {{ margin: 10px 0; font-size: 15px; }}
            .opportunity {{ color: #27ae60; background: #eafaf1; padding: 12px; border-radius: 6px; border-left: 3px solid #27ae60; }}
            .risk {{ color: #c0392b; background: #fdedec; padding: 12px; border-radius: 6px; border-left: 3px solid #c0392b; }}
            .footer {{ text-align: center; color: #bdc3c7; font-size: 12px; margin-top: 40px; border-top: 1px solid #eaeaea; padding-top: 20px; }}
            a {{ color: #3498db; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🌍 全球 AI 动向与商业情报日报</h1>
                <p>{datetime.now().strftime("%Y年%m月%d日")} | 共精选 {len(analyzed_html_blocks)} 组核心动向</p>
            </div>
            
            {final_news_html}
            
            <hr style="border:0; border-top:1px dashed #ccc; margin: 30px 0;">
            {source_links_html}
            
            <div class="footer">
                由 DeepSeek-Reasoner 与 GitHub Actions 自动驱动。<br>
                数据来源：TechCrunch, 机器之心, Wired, MIT News 等全球顶级媒体。
            </div>
        </div>
    </body>
    </html>
    """

    print(f"✉️ 正在发送邮件到 {RECEIVER_EMAIL}...", flush=True)
    mail_msg = MIMEText(final_html, 'html', 'utf-8')
    mail_msg['Subject'] = Header(f'【AI 日报】{datetime.now().strftime("%m-%d")} 数十条全球动向精选', 'utf-8')
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
