import pandas as pd
import webview
from binance.client import Client
import pandas_ta as ta
from lightweight_charts import Chart
import tkinter as tk
import queue
from datetime import datetime

# Patch the Chart.loop method
from lightweight_charts import chart
from webview import JavascriptException, window



def patched_loop(self):
    try:
        window.evaluate_js(arg)
    except webview.errors.JavascriptException as e:
        msg = e.result
        if 'line' not in msg:
            msg['line'] = -1  # or any default value
        if 'column' not in msg:
            msg['column'] = -1
        raise JavascriptException(f"\n\nscript -> '{arg}',\nerror -> {msg['name']}[{msg['line']}:{msg['column']}]\n{msg['message']}")

chart.Chart.loop = patched_loop


def main():
    print("Starting the main function...")

    # Define stop-loss and take-profit thresholds
    STOP_LOSS_PERCENTAGE = 0.02  # 2% stop-loss
    TAKE_PROFIT_PERCENTAGE = 0.05  # 5% take-profit

    # Initialize variables
    entry_price = None
    stop_loss_price = None
    take_profit_price = None

    # Initialize the queue
    # BEGIN: Queue initialization
    data_queue = queue.Queue()
    # END: Queue initialization

    # Initialize the charting library with full screen dimensions and use tkinter to get the full screen dimensions for Chart
    # BEGIN: Charting library initialization with full screen dimensions
    root = tk.Tk()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.destroy()
    # END: Charting library initialization with full screen dimensions

    print("Screen dimensions obtained.")

    # Chart configuration
    # BEGIN: Chart configuration
    chart = Chart(width=screen_width, height=screen_height)
    chart.layout(background_color='Black', text_color='#FFFFFF', font_size=16, font_family='Helvetica')
    chart.candle_style(up_color='#00ff55', down_color='#ed4807', border_up_color='#FFFFFF', border_down_color='#FFFFFF',
                       wick_up_color='#FFFFFF', wick_down_color='#FFFFFF')
    chart.volume_config(up_color='#00ff55', down_color='#ed4807')
    chart.watermark(text='', color='rgba(255, 255, 255, 0.7)')
    chart.crosshair(mode='normal', vert_color='#FFFFFF', vert_style='dotted', horz_color='#FFFFFF', horz_style='dotted')
    chart.legend(visible=True, font_size=14)
    # END: Chart configuration

    print("Chart configured.")

    # Fetch historical data from Binance
    # BEGIN: Fetch historical data from Binance
    client = Client()
    interval = Client.KLINE_INTERVAL_1HOUR
    start_date = '01 JAN 2010'
    end_date = '31 DEC 2024'
    ticker = "XRPUSDT"
    klines = client.get_historical_klines(symbol=ticker, interval=interval, start_str=start_date, end_str=end_date)

    if not klines:
        print("No data fetched from Binance.")
        return

    hist_df = pd.DataFrame(klines, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    hist_df.drop('ignore', axis=1, inplace=True)
    # END: Fetch historical data from Binance

    print("Historical data fetched.")

    # Convert necessary columns to datetime and numeric types
    # BEGIN: Data conversion
    hist_df['open_time'] = pd.to_datetime(hist_df['open_time'], unit='ms')
    hist_df.set_index('open_time', inplace=True)
    hist_df = hist_df.astype(float)
    hist_df.reset_index(inplace=True)
    hist_df.rename(columns={'open_time': 'time'}, inplace=True)
    # END: Data conversion

    print("Historical data prepared.")

    # Calculate technical indicators using pandas-ta
    # BEGIN: Calculate technical indicators
    hist_df['20_MA'] = ta.sma(hist_df['close'], length=20)
    hist_df['50_MA'] = ta.sma(hist_df['close'], length=50)
    hist_df['200_MA'] = ta.sma(hist_df['close'], length=200)
    hist_df['RSI'] = ta.rsi(hist_df['close'], length=14)
    macd = ta.macd(hist_df['close'], fast=12, slow=26, signal=9)
    hist_df['MACD'] = macd['MACD_12_26_9']
    hist_df['MACD_signal'] = macd['MACDs_12_26_9']
    hist_df['MACD_hist'] = macd['MACDh_12_26_9']
    bollinger = ta.bbands(hist_df['close'], length=20, std=2)
    hist_df['upperband'] = bollinger['BBU_20_2.0']
    hist_df['middleband'] = bollinger['BBM_20_2.0']
    hist_df['lowerband'] = bollinger['BBL_20_2.0']
    hist_df['ATR'] = ta.atr(hist_df['high'], hist_df['low'], hist_df['close'], length=14)

    supertrend_1 = ta.supertrend(hist_df['high'], hist_df['low'], hist_df['close'], length=10, multiplier=1)
    supertrend_2 = ta.supertrend(hist_df['high'], hist_df['low'], hist_df['close'], length=11, multiplier=2)
    supertrend_3 = ta.supertrend(hist_df['high'], hist_df['low'], hist_df['close'], length=12, multiplier=3)

    hist_df['Supertrend_10_1'] = supertrend_1['SUPERT_10_1.0']
    hist_df['Supertrend_11_2'] = supertrend_2['SUPERT_11_2.0']
    hist_df['Supertrend_12_3'] = supertrend_3['SUPERT_12_3.0']
    # END: Calculate technical indicators

    print(hist_df)

    bars = []

    latest_buy_signal = None
    latest_sell_signal = None

    # Modify the update_chart function to include stop-loss and take-profit logic
    def update_chart():
        nonlocal latest_buy_signal, latest_sell_signal, entry_price, stop_loss_price, take_profit_price
        try:
            while True:  # Keep checking the queue for new data
                try:
                    data = data_queue.get_nowait()
                    bars.append(data)
                except queue.Empty:
                    break
        except Exception as e:
            print(f"Error in update_chart: {e}")
        finally:
            # Once we have received all the data, convert to pandas dataframe
            df = pd.DataFrame(bars)
            print(f"DataFrame for chart update:\n{df}")

            # Set the data on the chart
            if not df.empty:
                print("Setting data on the chart...")
                chart.is_alive = True

                # Set the initial data for the chart
                chart.set(df[['time', 'open', 'high', 'low', 'close', 'volume']], keep_drawings=True)

                # Create and set Supertrend lines
                supertrend_10_1_line = chart.create_line(name='Supertrend_10_1', color='blue', style='solid', width=2,
                                                         price_line=True, price_label=True)
                supertrend_11_2_line = chart.create_line(name='Supertrend_11_2', color='green', style='solid', width=2,
                                                         price_line=True, price_label=True)
                supertrend_12_3_line = chart.create_line(name='Supertrend_12_3', color='red', style='solid', width=2,
                                                         price_line=True, price_label=True)

                supertrend_10_1_data = df[['time', 'Supertrend_10_1']].dropna()
                supertrend_11_2_data = df[['time', 'Supertrend_11_2']].dropna()
                supertrend_12_3_data = df[['time', 'Supertrend_12_3']].dropna()

                supertrend_10_1_line.set(supertrend_10_1_data)
                supertrend_11_2_line.set(supertrend_11_2_data)
                supertrend_12_3_line.set(supertrend_12_3_data)

                # Create lists to store markers and spans
                markers = []
                spans = []

                # Collect markers and spans
                for i in range(1, len(df)):
                    if (df['Supertrend_10_1'][i] < df['close'][i] and
                            df['Supertrend_11_2'][i] < df['close'][i] and
                            df['Supertrend_12_3'][i] < df['close'][i] and
                            (df['Supertrend_10_1'][i - 1] >= df['close'][i - 1] or
                             df['Supertrend_11_2'][i - 1] >= df['close'][i - 1] or
                             df['Supertrend_12_3'][i - 1] >= df['close'][i - 1])):
                        # Buy signal: Green background
                        spans.append({'start_time': df['time'][i].isoformat(),
                                      'end_time': df['time'][i + 1].isoformat() if i + 1 < len(df) else df['time'][
                                          i].isoformat(), 'color': 'rgba(0, 255, 0, 0.3)'})
                        markers.append({'time': df['time'][i].isoformat(), 'position': 'belowBar', 'shape': 'arrowUp',
                                        'color': 'green', 'text': 'Buy'})
                        latest_buy_signal = df.iloc[i]
                        entry_price = df['close'][i]
                        stop_loss_price = entry_price * (1 - STOP_LOSS_PERCENTAGE)
                        take_profit_price = entry_price * (1 + TAKE_PROFIT_PERCENTAGE)
                    elif (df['Supertrend_10_1'][i] > df['close'][i]
                          and df['Supertrend_11_2'][i] > df['close'][i]
                          and df['Supertrend_12_3'][i] > df['close'][i]
                          and (df['Supertrend_10_1'][i - 1] <= df['close'][i - 1]
                               or df['Supertrend_11_2'][i - 1] <= df['close'][i - 1]
                               or df['Supertrend_12_3'][i - 1] <= df['close'][i - 1])):
                        # Sell signal: Red background
                        spans.append({'start_time': df['time'][i].isoformat(),
                                      'end_time': df['time'][i + 1].isoformat() if i + 1 < len(df) else df['time'][
                                          i].isoformat(), 'color': 'rgba(255, 0, 0, 0.3)'})
                        markers.append({'time': df['time'][i].isoformat(), 'position': 'aboveBar', 'shape': 'arrowDown',
                                        'color': 'red', 'text': 'Sell'})
                        latest_sell_signal = df.iloc[i]
                        #entry_price = None
                        #stop_loss_price = None
                        #take_profit_price = None

                    # Add spans in batch
                for span in spans:
                    chart.vertical_span(start_time=span['start_time'], end_time=span['end_time'], color=span['color'])

                    # Add markers in batch
                chart.marker_list(markers)

                # Once we get the data back, we don't need a spinner anymore
                chart.spinner(False)

            else:
                print("DataFrame is empty, no data to set on the chart.")

            # Print the latest buy and sell signals with date and time
            if latest_buy_signal is not None:
                print(f"Latest Buy Signal: {latest_buy_signal['time']} - Price: {latest_buy_signal['close']}")
            if latest_sell_signal is not None:
                print(f"Latest Sell Signal: {latest_sell_signal['time']} - Price: {latest_sell_signal['close']}")

            # Check for stop-loss or take-profit conditions
            print(f"Entry Price: {entry_price}")
            if entry_price is not None:
                current_price = df['close'].iloc[-1]
                if current_price <= stop_loss_price:
                    print(f"Stop-loss triggered at {current_price}. Selling...")
                    entry_price = None
                    stop_loss_price = None
                    take_profit_price = None
                elif current_price >= take_profit_price:
                    print(f"Take-profit triggered at {current_price}. Selling...")
                    entry_price = None
                    stop_loss_price = None
                    take_profit_price = None

    # Prepare data for the chart and update it
    if not hist_df.empty:
        for _, row in hist_df.iterrows():
            data = {
                'time': row['time'].to_pydatetime(),  # Convert Timestamp to datetime
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
                'Supertrend_10_1': row['Supertrend_10_1'],
                'Supertrend_11_2': row['Supertrend_11_2'],
                'Supertrend_12_3': row['Supertrend_12_3'],
            }
            data_queue.put(data)

        update_chart()
        chart.show(block=True)
if __name__ == '__main__':
    main()
