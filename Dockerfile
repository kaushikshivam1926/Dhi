# Use an official lightweight Python image
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy dependency list first (for better caching)
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core script
COPY main.py .

# We declare a volume where the Vault and Config will be mounted
# This ensures data isn't lost when the container stops
VOLUME ["/app/config"]
VOLUME ["/app/Vault"]

# Use a symbolic link or expected path for config.json to point to the mountable config folder
CMD ["python", "main.py"]
