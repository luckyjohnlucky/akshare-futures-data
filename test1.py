import akshare as ak
import inspect
print("=== futures_zh_minute_sina signature ===")
try:
    sig = inspect.signature(ak.futures_zh_minute_sina)
    print(sig)
except Exception as e:
    print(f"Error: {e}")

print("\n=== Docstring ===")
try:
    print(ak.futures_zh_minute_sina.__doc__)
except Exception as e:
    print(f"Error: {e}")