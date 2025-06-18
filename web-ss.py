from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.headless = True  # Don't open a window
driver = webdriver.Chrome(options=options)

driver.get("https://google.com")

# Save screenshot
driver.save_screenshot("screenshot.png")

driver.quit()
