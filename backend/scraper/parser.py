import requests

response = requests.get("https://skapa-academy.com/")
print(response.status_code)