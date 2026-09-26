FROM python:3.12-slim

WORKDIR /app

# Install system dependencies required by OpenCV and other libraries
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file
COPY requirements-gradio.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-gradio.txt
RUN pip install --no-cache-dir gradio

# Copy the application code
COPY . .

# Expose the Gradio port
EXPOSE 7860

# Run the Gradio app
CMD ["python", "app.py"]
