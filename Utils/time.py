import time
import logging

def timeit(func):
    """Decorator to measure the runtime of a function."""
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        duration = end - start
        logging.info(f"Function '{func.__name__}' executed in {duration:.4f} seconds")
        return result
    return wrapper



