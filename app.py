# -*- coding: utf-8 -*-
"""
ETH EHR999 指标计算与图表生成
独立运行，生成 TradingView 风格的 HTML 图表
"""
import time  # 确保在文件顶部导入了 time 模块
import json
import pandas as pd
import numpy as np
import requests
from datetime import datetime
from pathlib import Path


# ================================================
# 配置
# ================================================
SYMBOL = 'ETHUSDT'
OUTPUT_FILE = 'index.html'


# ================================================
# 数据获取
# ================================================
def fetch_eth_klines(symbol='ETHUSDT', interval='1d', limit=1000):
    """
    从币安 API 获取全量 K 线数据
    通过分批请求获取所有历史数据
    """
    url = 'https://api.binance.com/api/v3/klines'
    all_data = []
    
    print(f"正在从币安获取 {symbol} {interval} 全量K线数据...")
    
    # ETH 上线时间约为 2017-08-17
    start_time = int(datetime(2017, 8, 17).timestamp() * 1000)
    
    try:
        while True:
            params = {
                'symbol': symbol,
                'interval': interval,
                'startTime': start_time,
                'limit': 1000  # 币安单次最多1000条
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                break
            
            all_data.extend(data)
            print(f"  已获取 {len(all_data)} 条数据...")
            
            # 更新起始时间为最后一条数据的时间 + 1
            start_time = data[-1][0] + 1
            
            # 如果返回数据少于1000条，说明已经获取完毕
            if len(data) < 1000:
                break
        
        if not all_data:
            print("未获取到数据")
            return None
        
        df = pd.DataFrame(all_data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close'] = df['close'].astype(float)
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # 去重
        df = df.drop_duplicates(subset=['open_time']).reset_index(drop=True)
        
        print(f"获取成功: {len(df)} 条数据")
        print(f"时间范围: {df['open_time'].min()} 到 {df['open_time'].max()}")
        
        return df
        
    except Exception as e:
        print(f"获取数据失败: {e}")
        return None


# ================================================
# EHR999 指标计算
# ================================================
def calculate_ehr999(df):
    """
    计算 EHR999 指标
    
    EHR999 = (当前价格 / MA200) * (当前价格 / 长期均线)
    """
    print("正在计算 EHR999 指标...")
    
    df = df.copy()
    data_length = len(df)
    
    # 根据数据量调整移动平均窗口
    if data_length < 200:
        ma_window = min(50, data_length // 4)
    else:
        ma_window = 200
    
    # 计算 MA200
    df['MA200'] = df['close'].rolling(window=ma_window).mean()
    
    # 计算长期移动平均
    max_long_window = int(len(df) * 0.6)
    long_window = min(ma_window * 7, max_long_window)
    if long_window < ma_window + 50:
        long_window = min(ma_window + 50, len(df) - 10)
    
    print(f"使用 MA{ma_window} 和 MA{long_window} 计算 EHR999")
    df['MA_long'] = df['close'].rolling(window=long_window).mean()
    
    # 计算 EHR999
    df['EHR999'] = (df['close'] / df['MA200']) * (df['close'] / df['MA_long'])
    
    # 删除 NaN
    df = df.dropna(subset=['EHR999'])
    
    print(f"EHR999 计算完成，有效数据: {len(df)} 条")
    
    return df


# ================================================
# 生成 HTML 图表
# ================================================
def generate_html_chart(df, symbol='ETHUSDT', output_path=None):
    """
    生成 TradingView 风格的 EHR999 HTML 图表
    """
    print("正在生成 HTML 图表...")
    
    if df is None or df.empty:
        print("错误：数据为空")
        return None
    
    # 准备数据
    ehr999_data = []
    for _, row in df.iterrows():
        if pd.notna(row['EHR999']):
            timestamp = int(row['open_time'].timestamp())
            ehr999_data.append({
                'time': timestamp,
                'value': float(row['EHR999'])
            })
    
    # 获取最新值
    start_time = df['open_time'].min().strftime('%Y-%m-%d')
    end_time = df['open_time'].max().strftime('%Y-%m-%d')
    latest_ehr999 = df['EHR999'].iloc[-1]
    latest_price = df['close'].iloc[-1]
    latest_time = df['open_time'].iloc[-1].strftime('%Y-%m-%d %H:%M')
    
    # 计算定投倍数和市场状态
    if latest_ehr999 < 0.73:
        invest_multiplier = "2.0x ~ 3.0x"
        market_status = "极度低估 (钻石坑)"
        status_color = "#00c853"
    elif latest_ehr999 < 1.20:
        invest_multiplier = "1.5x"
        market_status = "相对低估 (黄金坑)"
        status_color = "#ffd600"
    elif latest_ehr999 < 1.50:
        invest_multiplier = "1.0x"
        market_status = "合理估值 (定投区)"
        status_color = "#2196f3"
    elif latest_ehr999 < 3.0:
        invest_multiplier = "0x (停止)"
        market_status = "持币待涨"
        status_color = "#9e9e9e"
    elif latest_ehr999 < 4.5:
        invest_multiplier = "减仓"
        market_status = "泡沫初现 (减仓区)"
        status_color = "#ff9800"
    elif latest_ehr999 < 6.5:
        invest_multiplier = "清仓50-80%"
        market_status = "极度泡沫 (清仓区)"
        status_color = "#ff5722"
    else:
        invest_multiplier = "全部卖出"
        market_status = "疯狂顶部 (逃顶区)"
        status_color = "#d50000"
    
    # JSON 数据
    ehr999_data_json = json.dumps(ehr999_data)
    
    # 阈值线配置
    market_levels = [
        (0.73, '#00c853', '钻石坑/黄金坑'),
        (1.20, '#ffd600', '黄金坑/定投区'),
        (1.50, '#2196f3', '定投截止线'),
        (3.0, '#ff9800', '减仓区'),
        (4.5, '#ff5722', '清仓区'),
        (6.5, '#d50000', '逃顶区'),
    ]
    
    level_lines_js = ""
    for ehr_value, color, title in market_levels:
        level_lines_js += f"""
        ehr999Series.createPriceLine({{
            price: {ehr_value},
            color: '{color}',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: '{title}'
        }});
        """
    
    # 图例
    legend_items = ""
    for ehr_value, color, title in market_levels:
        legend_items += f'''
            <div class="legend-item">
                <div class="legend-color" style="background: {color};"></div>
                <span>{ehr_value} ({title})</span>
            </div>'''

    
    # HTML 模板
    html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{symbol} EHR999 - TradingView Style Chart</title>
    <script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #131722;
            color: #d1d4dc;
        }}
        .container {{ padding: 10px; max-width: 1400px; margin: 0 auto; }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            background: #1e222d;
            border-radius: 4px;
            margin-bottom: 10px;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .title {{ font-size: 18px; font-weight: 600; color: #fff; }}
        .info {{ display: flex; gap: 20px; font-size: 13px; flex-wrap: wrap; }}
        .info-item {{ display: flex; align-items: center; gap: 5px; }}
        .info-label {{ color: #787b86; }}
        .info-value {{ font-weight: 500; color: #f7931a; }}
        .info-value.price {{ color: #26a69a; }}
        .info-value.multiplier {{ color: #2196f3; }}
        .info-value.time {{ color: #787b86; }}
        .status-badge-header {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }}
        .chart-container {{
            background: #1e222d;
            border-radius: 4px;
            padding: 10px;
            margin-bottom: 10px;
        }}
        .chart-title {{ font-size: 12px; color: #787b86; margin-bottom: 5px; padding-left: 5px; }}
        #ehr999-chart {{ height: 500px; }}
        .legend {{
            display: flex;
            gap: 15px;
            padding: 10px 15px;
            background: #1e222d;
            border-radius: 4px;
            font-size: 12px;
            flex-wrap: wrap;
        }}
        .legend-item {{ display: flex; align-items: center; gap: 5px; }}
        .legend-color {{ width: 12px; height: 3px; border-radius: 1px; }}
        .time-range {{ font-size: 11px; color: #787b86; text-align: right; padding: 5px 15px; }}
        .strategy-table-container {{
            background: #1e222d;
            border-radius: 4px;
            padding: 15px;
            margin-top: 10px;
        }}
        .strategy-table-title {{ font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 10px; padding-left: 5px; }}
        .strategy-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        .strategy-table th {{
            background: #2a2e39;
            color: #787b86;
            padding: 10px 8px;
            text-align: left;
            font-weight: 500;
            border-bottom: 1px solid #363a45;
        }}
        .strategy-table td {{ padding: 10px 8px; border-bottom: 1px solid #2a2e39; }}
        .strategy-table tr:hover {{ background: #2a2e39; }}
        .status-badge {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 500;
        }}
        .status-diamond {{ background: #00c853; color: #000; }}
        .status-gold {{ background: #ffd600; color: #000; }}
        .status-normal {{ background: #2196f3; color: #fff; }}
        .status-stop {{ background: #9e9e9e; color: #fff; }}
        .status-reduce {{ background: #ff9800; color: #000; }}
        .status-clear {{ background: #ff5722; color: #fff; }}
        .status-escape {{ background: #d50000; color: #fff; }}
        .multiplier {{ font-weight: 600; color: #26a69a; }}
        .multiplier-zero {{ color: #ef5350; }}
        .current-row {{ background: rgba(247, 147, 26, 0.15) !important; }}
        .current-row td {{ color: #f7931a; font-weight: 500; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title">EntorpyBreaker™ {symbol} EHR999 指标</div>
            <div class="info">
                <div class="info-item">
                    <span class="info-label">价格:</span>
                    <span class="info-value price">${latest_price:.2f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">EHR999:</span>
                    <span class="info-value">{latest_ehr999:.4f}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">定投倍数:</span>
                    <span class="info-value multiplier">{invest_multiplier}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">市场状态:</span>
                    <span class="status-badge-header" style="background: {status_color}; color: #000;">{market_status}</span>
                </div>
                <div class="info-item">
                    <span class="info-label">更新时间:</span>
                    <span class="info-value time">{latest_time}</span>
                </div>
            </div>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">EHR999 指标</div>
            <div id="ehr999-chart"></div>
        </div>
        
        <div class="legend">{legend_items}
        </div>
        
        <div class="time-range">数据范围: {start_time} 至 {end_time}</div>
        
        <div class="strategy-table-container">
            <div class="strategy-table-title">📊 EHR999 市场状态与操作策略</div>
            <table class="strategy-table">
                <thead>
                    <tr>
                        <th>市场状态</th>
                        <th>EHR999 区间</th>
                        <th>历史概率</th>
                        <th>建议操作</th>
                        <th>定投倍数</th>
                    </tr>
                </thead>
                <tbody>
                    <tr class="{'current-row' if latest_ehr999 < 0.73 else ''}">
                        <td><span class="status-badge status-diamond">极度低估 (钻石坑)</span></td>
                        <td>&lt; 0.73</td>
                        <td>底部 10%</td>
                        <td>重仓抄底</td>
                        <td class="multiplier">2.0x ~ 3.0x</td>
                    </tr>
                    <tr class="{'current-row' if 0.73 <= latest_ehr999 < 1.20 else ''}">
                        <td><span class="status-badge status-gold">相对低估 (黄金坑)</span></td>
                        <td>0.73 ~ 1.20</td>
                        <td>10% ~ 40%</td>
                        <td>加大定投</td>
                        <td class="multiplier">1.5x</td>
                    </tr>
                    <tr class="{'current-row' if 1.20 <= latest_ehr999 < 1.50 else ''}">
                        <td><span class="status-badge status-normal">合理估值 (定投区)</span></td>
                        <td>1.20 ~ 1.50</td>
                        <td>40% ~ 55%</td>
                        <td>标准定投</td>
                        <td class="multiplier">1.0x</td>
                    </tr>
                    <tr class="{'current-row' if 1.50 <= latest_ehr999 < 3.0 else ''}">
                        <td><span class="status-badge status-stop">定投截止 / 持币待涨</span></td>
                        <td>1.50 ~ 3.0</td>
                        <td>前 45%</td>
                        <td>停止定投，只拿不动</td>
                        <td class="multiplier-zero">0x</td>
                    </tr>
                    <tr class="{'current-row' if 3.0 <= latest_ehr999 < 4.5 else ''}">
                        <td><span class="status-badge status-reduce">泡沫初现 (减仓区)</span></td>
                        <td>3.0 ~ 4.5</td>
                        <td>顶部 15%</td>
                        <td>小额止盈</td>
                        <td>每涨10%卖5%</td>
                    </tr>
                    <tr class="{'current-row' if 4.5 <= latest_ehr999 < 6.5 else ''}">
                        <td><span class="status-badge status-clear">极度泡沫 (清仓区)</span></td>
                        <td>4.5 ~ 6.5</td>
                        <td>顶部 5%</td>
                        <td>大力止盈</td>
                        <td>清仓 50%~80%</td>
                    </tr>
                    <tr class="{'current-row' if latest_ehr999 >= 6.5 else ''}">
                        <td><span class="status-badge status-escape">疯狂顶部 (逃顶区)</span></td>
                        <td>&gt; 6.5</td>
                        <td>顶部 1%</td>
                        <td>清空离场</td>
                        <td>全部卖出</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const chartOptions = {{
            layout: {{
                background: {{ type: 'solid', color: '#1e222d' }},
                textColor: '#d1d4dc',
            }},
            grid: {{
                vertLines: {{ color: '#2B2B43' }},
                horzLines: {{ color: '#2B2B43' }},
            }},
            crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
            rightPriceScale: {{ borderColor: '#2B2B43' }},
            timeScale: {{
                borderColor: '#2B2B43',
                timeVisible: true,
                secondsVisible: false,
            }},
        }};

        const ehr999Chart = LightweightCharts.createChart(
            document.getElementById('ehr999-chart'),
            {{ ...chartOptions, height: 500 }}
        );
        
        const ehr999Series = ehr999Chart.addLineSeries({{
            color: '#f7931a',
            lineWidth: 2,
            priceFormat: {{ type: 'price', precision: 4, minMove: 0.0001 }},
        }});
        
        const ehr999Data = {ehr999_data_json};
        ehr999Series.setData(ehr999Data);
        
        {level_lines_js}

        function resizeChart() {{
            const width = document.getElementById('ehr999-chart').clientWidth;
            ehr999Chart.applyOptions({{ width }});
        }}
        
        window.addEventListener('resize', resizeChart);
        resizeChart();
        ehr999Chart.timeScale().fitContent();
    </script>
</body>
</html>'''
    
    # --- 简化的保存逻辑 ---
    # 强制直接在当前目录下创建文件
    with open("index.html", 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ HTML 图表已成功写入到当前目录: index.html")
    return "index.html"
    
    print(f"✅ HTML 图表已保存到: {output_path}")
    return str(output_path)


if __name__ == '__main__':

    print("\n" + "=" * 60)
    print(f"开始更新任务: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 1. 获取全量数据
    df = fetch_eth_klines(SYMBOL, interval='1d')
    
    if df is not None:
        # 2. 计算 EHR999
        df = calculate_ehr999(df)
        
        # 3. 显示最新数据
        print("\n最新趋势:")
        print(f"   价格: ${df['close'].iloc[-1]:.2f}")
        print(f"   EHR999: {df['EHR999'].iloc[-1]:.4f}")
        print(f"   时间: {df['open_time'].iloc[-1]}")
        
        # 4. 生成 HTML 图表
        generate_html_chart(df, SYMBOL)
        print("\n✅ 更新完成！HTML 图表已保存。")
    else:
        print("❌ 获取数据失败，等待下一次尝试...")


