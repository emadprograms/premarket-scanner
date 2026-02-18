const axios = require('axios');

async function testBackend() {
    console.log("Testing Backend Connectivity...");
    try {
        const response = await axios.get('http://127.0.0.1:8000/api/system/status');
        console.log("✅ Success! Status:", response.status);
        console.log("Data:", JSON.stringify(response.data, null, 2));
    } catch (error) {
        console.error("❌ Failed:", error.message);
        if (error.response) {
            console.error("Response:", error.response.status, error.response.data);
        }
    }
}

testBackend();
