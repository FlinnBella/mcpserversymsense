# healthcare_mcp_server.py
import asyncio
import base64
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from collections.abc import AsyncIterator

import httpx
from mcp.server.fastmcp import FastMCP, Context, Image
from mcp.server.fastmcp.prompts import base
from supabase import create_client, Client


@dataclass 
class AppContext:
    supabase: Client
    http_client: httpx.AsyncClient


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Manage application lifecycle with Supabase and HTTP client"""
    # Initialize Supabase client
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY environment variables are required")
    
    supabase = create_client(supabase_url, supabase_key)
    
    # Initialize HTTP client
    http_client = httpx.AsyncClient(timeout=30.0)
    
    try:
        yield AppContext(supabase=supabase, http_client=http_client)
    finally:
        await http_client.aclose()


# Create MCP server with lifespan management
mcp = FastMCP(
    "Healthcare Assistant",
    dependencies=["supabase", "httpx", "pillow"],
    lifespan=app_lifespan
)


# Resources - User Data from Supabase
@mcp.resource("user://profile/{user_id}")
def get_user_profile(user_id: str) -> str:
    """Get user profile information from Supabase"""
    ctx = mcp.get_context()
    supabase = ctx.request_context.lifespan_context["supabase"]
    
    try:
        response = supabase.table("users").select("*").eq("id", user_id).execute()
        if response.data:
            user_data = response.data[0]
            return f"""
User Profile:
- Name: {user_data.get('full_name', 'N/A')}
- Email: {user_data.get('email', 'N/A')}
- Age: {user_data.get('age', 'N/A')}
- Medical History: {user_data.get('medical_history', 'No history recorded')}
- Allergies: {user_data.get('allergies', 'None reported')}
- Current Medications: {user_data.get('current_medications', 'None reported')}
"""
        else:
            return f"No user found with ID: {user_id}"
    except Exception as e:
        return f"Error retrieving user profile: {str(e)}"


@mcp.resource("user://medical-history/{user_id}")
def get_user_medical_history(user_id: str) -> str:
    """Get detailed medical history for a user"""
    ctx = mcp.get_context()
    supabase = ctx.request_context.lifespan_context["supabase"]
    
    try:
        response = supabase.table("medical_records").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        if response.data:
            records = []
            for record in response.data:
                records.append(f"""
Date: {record.get('created_at', 'Unknown')}
Condition: {record.get('condition', 'N/A')}
Treatment: {record.get('treatment', 'N/A')}
Doctor: {record.get('doctor_name', 'N/A')}
Notes: {record.get('notes', 'No notes')}
---""")
            return f"Medical History for User {user_id}:\n" + "\n".join(records)
        else:
            return f"No medical history found for user: {user_id}"
    except Exception as e:
        return f"Error retrieving medical history: {str(e)}"


# Tools - Doctor Search and Appointment Booking
@mcp.tool()
async def search_nearby_doctors(
    latitude: float,
    longitude: float,
    specialty: str = "general",
    radius_miles: int = 10,
    ctx: Context = None
) -> str:
    """Search for nearby doctors using external API"""
    http_client = ctx.request_context.lifespan_context["http_client"]
    
    # Using BetterDoctor API or similar healthcare provider API
    api_key = os.getenv("DOCTOR_API_KEY")
    if not api_key:
        return "Doctor API key not configured. Please contact administrator."
    
    try:
        url = "https://api.betterdoctor.com/2016-05-02/doctors"
        params = {
            "location": f"{latitude},{longitude},{radius_miles}",
            "specialty_uid": specialty,
            "limit": 10,
            "user_key": api_key
        }
        
        response = await http_client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("data"):
            return "No doctors found in your area. Please try expanding your search radius."
        
        doctors = []
        for i, doctor in enumerate(data["data"][:5], 1):
            profile = doctor.get("profile", {})
            practices = doctor.get("practices", [{}])
            practice = practices[0] if practices else {}
            
            doctor_info = f"""
{i}. Dr. {profile.get('first_name', '')} {profile.get('last_name', '')}
   Specialty: {', '.join([s.get('name', '') for s in doctor.get('specialties', [])])}
   Practice: {practice.get('name', 'N/A')}
   Address: {practice.get('visit_address', {}).get('street', 'N/A')}
   Phone: {practice.get('phones', [{}])[0].get('number', 'N/A')}
   Distance: {practice.get('distance', 'N/A')} miles
   Rating: {'★' * int(float(practice.get('rating', {}).get('average', 0)))}
   
   Website: {practice.get('website', 'No website available')}
   Accepts New Patients: {'Yes' if practice.get('accepts_new_patients') else 'No'}
"""
            doctors.append(doctor_info)
        
        result = "🏥 Nearby Doctors Found:\n" + "\n".join(doctors)
        result += "\n\n📅 Would you like to book an appointment with any of these doctors? I can help you with the appointment workflow!"
        
        return result
        
    except Exception as e:
        return f"Error searching for doctors: {str(e)}"


@mcp.tool()
async def get_doctor_availability(doctor_id: str, ctx: Context = None) -> str:
    """Get available appointment slots for a specific doctor"""
    http_client = ctx.request_context.lifespan_context["http_client"]
    
    try:
        # This would integrate with the doctor's booking system API
        api_key = os.getenv("DOCTOR_API_KEY")
        url = f"https://api.betterdoctor.com/2016-05-02/doctors/{doctor_id}/appointments"
        
        response = await http_client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        
        # Mock response for demonstration
        return f"""
📅 Available Appointment Slots for Dr. {doctor_id}:

This Week:
- Tomorrow 2:00 PM - 15 min consultation
- Thursday 10:30 AM - 30 min consultation  
- Friday 3:45 PM - 15 min consultation

Next Week:
- Monday 9:00 AM - 30 min consultation
- Tuesday 1:15 PM - 15 min consultation
- Wednesday 4:30 PM - 30 min consultation

🔗 Book Online: [Click here to book directly](https://doctorbooking.example.com/book/{doctor_id})
📞 Call to Book: (555) 123-4567

Would you like me to help you book one of these appointments?
"""
    except Exception as e:
        return f"Error retrieving doctor availability: {str(e)}"


@mcp.tool()
async def analyze_skin_condition_image(image_data: str, ctx: Context = None) -> str:
    """Analyze uploaded image for potential skin conditions using AI"""
    http_client = ctx.request_context.lifespan_context["http_client"]
    
    try:
        # Use a medical image analysis API (e.g., SkinVision API, DermEngine)
        api_key = os.getenv("SKIN_ANALYSIS_API_KEY")
        if not api_key:
            return "Skin analysis API not configured. Please contact administrator."
        
        # Prepare image for API
        url = "https://api.skinvision.com/v1/analyze"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "image": image_data,  # Base64 encoded image
            "metadata": {
                "body_part": "unknown",
                "image_quality": "auto_detect"
            }
        }
        
        response = await http_client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        # Process the API response
        confidence = result.get("confidence", 0)
        condition = result.get("predicted_condition", "Unknown")
        risk_level = result.get("risk_level", "Unknown")
        recommendations = result.get("recommendations", [])
        
        analysis_result = f"""
🔬 Skin Condition Analysis Results:

📊 Analysis Confidence: {confidence}%
🏷️ Potential Condition: {condition}
⚠️ Risk Level: {risk_level}

📋 Recommendations:
"""
        
        for rec in recommendations:
            analysis_result += f"• {rec}\n"
        
        analysis_result += f"""

⚠️ IMPORTANT DISCLAIMER: This analysis is for informational purposes only and should not replace professional medical advice. Please consult with a dermatologist for proper diagnosis and treatment.

🏥 Would you like me to help you find nearby dermatologists for a professional consultation?
"""
        
        return analysis_result
        
    except Exception as e:
        return f"Error analyzing skin condition: {str(e)}. Please ensure the image is clear and try again."


@mcp.tool()
def create_appointment_booking_resource(doctor_name: str, practice_website: str) -> str:
    """Create a visual resource for booking appointments with specific doctor"""
    return f"""
📋 Appointment Booking Options for {doctor_name}:

🌐 Online Booking:
┌─────────────────────────────────────┐
│  📅 Book Online                     │
│  {practice_website}                 │
│  ✅ Instant confirmation            │
│  ⏰ 24/7 availability               │
└─────────────────────────────────────┘

📞 Phone Booking:
┌─────────────────────────────────────┐
│  ☎️ Call Practice Directly          │
│  📞 (555) 123-4567                  │
│  🕒 Mon-Fri 8AM-5PM                 │
│  💬 Speak with receptionist         │
└─────────────────────────────────────┘

📱 Mobile App:
┌─────────────────────────────────────┐
│  📲 Download Practice App           │
│  🔍 Search "[Practice Name] app"    │
│  📅 Mobile-friendly booking         │
│  📬 Appointment reminders           │
└─────────────────────────────────────┘

💡 Pro Tip: Online booking is usually fastest and gives you real-time availability!
"""


# Prompts - Skincare Product Recommendations
@mcp.prompt()
def skincare_product_consultation(skin_type: str = "", concerns: str = "", budget: str = "") -> list[base.Message]:
    """Comprehensive skincare product consultation prompt"""
    return [
        base.UserMessage(f"""
I'm looking for skincare product recommendations. Here are my details:
- Skin Type: {skin_type if skin_type else "Not specified"}
- Main Concerns: {concerns if concerns else "General skincare"}
- Budget Range: {budget if budget else "Not specified"}

Please provide personalized recommendations and let me know about purchasing options.
"""),
        base.AssistantMessage("""
I'd be happy to help you with personalized skincare recommendations! Based on your skin type and concerns, I can suggest products that would work well for you.

Here are my recommendations:

🧴 **Recommended Products:**

For your skin type and concerns, I suggest:
1. **Gentle Cleanser** - Daily use, morning and evening
2. **Hydrating Serum** - With hyaluronic acid for moisture retention  
3. **Targeted Treatment** - For your specific concerns
4. **Moisturizer** - Suitable for your skin type
5. **SPF Protection** - Daily sun protection (essential!)

💡 **Usage Tips:**
- Start with one new product at a time
- Patch test before full application
- Consistency is key for best results

🛒 **Ready to Purchase?**
Would you like to browse and purchase these recommended products from our curated skincare collection? 

Our website offers:
✅ Dermatologist-approved products
✅ Customer reviews and ratings  
✅ Detailed ingredient lists
✅ Fast shipping and easy returns

**Would you like me to direct you to our products page to explore these recommendations?**
"""),
        base.UserMessage("That sounds great! Yes, I'd like to see the products page."),
        base.AssistantMessage("""
Perfect! I'm redirecting you to our skincare products page where you can explore all the recommended products.

🔗 **Redirecting to Products Page...**

┌─────────────────────────────────────────────┐
│  🛒 SKINCARE PRODUCTS PAGE                  │
│                                             │
│  🌟 Personalized Recommendations           │
│  💎 Premium & Drugstore Options            │
│  📋 Detailed Product Information            │
│  ⭐ Customer Reviews & Ratings              │
│  🚚 Free Shipping on Orders $50+           │
│                                             │
│  [Click here to browse products]            │
│  👆 https://yourwebsite.com/skincare       │
└─────────────────────────────────────────────┘

You'll find your personalized recommendations highlighted on the page. Each product includes detailed descriptions, ingredients, usage instructions, and customer reviews to help you make the best choice for your skin!

Happy shopping! 🛍️✨
""")
    ]


@mcp.prompt()
def appointment_workflow_prompt(doctor_name: str = "", specialty: str = "") -> list[base.Message]:
    """Prompt to guide users through appointment booking workflow"""
    return [
        base.UserMessage(f"I'd like to book an appointment with {doctor_name} ({specialty}). Can you help me with the process?"),
        base.AssistantMessage(f"""
Absolutely! I'll guide you through booking an appointment with {doctor_name}. Let me walk you through the available options:

📅 **Appointment Booking Workflow**

**Step 1: Choose Your Booking Method**
1. 🌐 Online Booking (Fastest)
2. 📞 Phone Booking (Personal Touch)  
3. 📱 Mobile App (Convenient)

**Step 2: Information You'll Need**
✅ Your insurance information
✅ Reason for visit
✅ Preferred date and time
✅ Contact information
✅ Any current medications

**Step 3: Appointment Confirmation**
You'll receive confirmation via:
- 📧 Email confirmation
- 📱 Text message reminder
- 📞 Phone call (if requested)

**Ready to proceed?** Which booking method would you prefer? I can provide direct links and detailed instructions for your chosen method.

Additionally, I can help you:
- Check the doctor's availability
- Understand what to expect during your visit
- Prepare questions for your appointment
- Find directions to the practice

How would you like to proceed?
""")
    ]


# Tool to save user interactions for future reference
@mcp.tool()
async def save_user_interaction(user_id: str, interaction_type: str, details: str, ctx: Context = None) -> str:
    """Save user interaction to Supabase for future reference"""
    supabase = ctx.request_context.lifespan_context["supabase"]
    
    try:
        data = {
            "user_id": user_id,
            "interaction_type": interaction_type,
            "details": details,
            "timestamp": "now()"
        }
        
        response = supabase.table("user_interactions").insert(data).execute()
        
        if response.data:
            return f"✅ Interaction saved successfully for user {user_id}"
        else:
            return "❌ Failed to save interaction"
            
    except Exception as e:
        return f"Error saving interaction: {str(e)}"


if __name__ == "__main__":
    # Required environment variables
    required_env_vars = [
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY", 
        "DOCTOR_API_KEY",
        "SKIN_ANALYSIS_API_KEY"
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these variables before running the server.")
        exit(1)
    
    mcp.run()