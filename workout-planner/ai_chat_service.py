"""
AI Chat Service
Provides intelligent fitness coaching through conversation.
Integrates with user's health data, goals, and readiness for context-aware responses.
"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from database import get_db, get_cursor

# Support both OpenAI and Anthropic
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

class AIChatService:
    """AI-powered fitness coach chatbot with health data context"""
    
    def __init__(self):
        self.provider = os.getenv("AI_PROVIDER", "openai").lower()
        self.client = None
        self.model = "mock"
        
        if self.provider == "openai" and OPENAI_AVAILABLE:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.client = openai.OpenAI(api_key=api_key)
                self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            else:
                print("Warning: OPENAI_API_KEY not set. Using mock responses.")
        elif self.provider == "anthropic" and ANTHROPIC_AVAILABLE:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                self.client = anthropic.Anthropic(api_key=api_key)
                self.model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
            else:
                print("Warning: ANTHROPIC_API_KEY not set. Using mock responses.")
        else:
            # Fallback to mock mode for development
            print("Warning: No AI provider configured. Using mock responses.")
    
    def get_user_context(self, user_id: str, days: int = 7) -> Dict[str, Any]:
        """Retrieve user's recent health data, goals, and readiness for context"""
        context = {
            "goals": [],
            "recent_health": {},
            "readiness": None,
            "summary": ""
        }
        
        with get_db() as conn:
            cur = get_cursor(conn)
            
            # Get active goals
            cur.execute("""
                SELECT goal_type, target_value, target_unit, target_date, notes
                FROM user_goals
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC
            """, (user_id,))
            
            goals = cur.fetchall()
            if goals:
                context["goals"] = [dict(g) for g in goals]
            
            # Get recent health samples (last N days)
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            cur.execute("""
                SELECT sample_type, AVG(value) as avg_value, COUNT(*) as count, unit
                FROM health_samples
                WHERE user_id = ? AND start_time >= ?
                GROUP BY sample_type, unit
            """, (user_id, cutoff))
            
            health = cur.fetchall()
            if health:
                context["recent_health"] = {
                    row['sample_type']: {
                        'avg': round(row['avg_value'], 2),
                        'count': row['count'],
                        'unit': row['unit']
                    }
                    for row in health
                }
            
            # Calculate simple readiness from available metrics
            hrv = context["recent_health"].get("hrv", {}).get("avg")
            resting_hr = context["recent_health"].get("resting_hr", {}).get("avg")
            sleep = context["recent_health"].get("sleep", {}).get("avg")
            
            if hrv or resting_hr or sleep:
                readiness_score = 0.5  # baseline
                if hrv and hrv > 40:
                    readiness_score += 0.2
                if resting_hr and resting_hr < 60:
                    readiness_score += 0.2
                if sleep and sleep >= 7:
                    readiness_score += 0.1
                context["readiness"] = min(readiness_score, 1.0)
        
        # Build context summary
        summary_parts = []
        if context["goals"]:
            summary_parts.append(f"User has {len(context['goals'])} active goal(s)")
        if context["recent_health"]:
            metrics = ", ".join(context["recent_health"].keys())
            summary_parts.append(f"Recent metrics: {metrics}")
        if context["readiness"] is not None:
            summary_parts.append(f"Readiness: {context['readiness']:.0%}")
        
        context["summary"] = ". ".join(summary_parts) if summary_parts else "No recent data available"
        
        return context
    
    def build_system_prompt(self, context: Dict[str, Any]) -> str:
        """Build system prompt with user context"""
        prompt = """You are an expert AI fitness coach integrated into a fitness tracking app. 
You have access to the user's health data, goals, and readiness metrics.

Your role:
- Provide personalized fitness advice based on their current state
- Help them achieve their goals through smart recommendations
- Answer questions about their training, recovery, nutrition
- Be encouraging but honest about what the data shows
- Suggest adjustments to training based on readiness and metrics

Current User Context:
"""
        prompt += f"{context['summary']}\n\n"
        
        if context["goals"]:
            prompt += "Active Goals:\n"
            for goal in context["goals"]:
                prompt += f"- {goal['goal_type']}: {goal['target_value']} {goal['target_unit']} by {goal['target_date']}\n"
            prompt += "\n"
        
        if context["recent_health"]:
            prompt += "Recent Health Metrics (last 7 days average):\n"
            for metric, data in context["recent_health"].items():
                prompt += f"- {metric}: {data['avg']} {data['unit']} ({data['count']} samples)\n"
            prompt += "\n"
        
        if context["readiness"] is not None:
            prompt += f"Current Readiness Score: {context['readiness']:.0%}\n\n"
        
        prompt += "Be concise, actionable, and supportive in your responses."
        
        return prompt
    
    async def generate_response(
        self, 
        user_id: str, 
        message: str, 
        session_id: Optional[int] = None,
        chat_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Generate AI response to user message with context"""
        
        # Get user context
        context = self.get_user_context(user_id)
        system_prompt = self.build_system_prompt(context)
        
        # Build messages array
        messages = []
        
        # Add recent chat history if provided
        if chat_history:
            for msg in chat_history[-10:]:  # Last 10 messages for context
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # Add current message
        messages.append({
            "role": "user",
            "content": message
        })
        
        # Generate response based on provider
        response_text = ""
        metadata = {"context": context["summary"]}
        
        if self.model == "mock":
            # Mock response for development
            response_text = self._generate_mock_response(message, context)
            metadata["mock"] = True
        
        elif self.provider == "openai" and self.client:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        *messages
                    ],
                    temperature=0.7,
                    max_tokens=500
                )
                response_text = response.choices[0].message.content
                metadata["model"] = self.model
                metadata["tokens"] = response.usage.total_tokens
            except Exception as e:
                response_text = f"Sorry, I encountered an error: {str(e)}"
                metadata["error"] = str(e)
        
        elif self.provider == "anthropic" and self.client:
            try:
                response = self.client.messages.create(
                    model=self.model,
                    system=system_prompt,
                    messages=messages,
                    max_tokens=500,
                    temperature=0.7
                )
                response_text = response.content[0].text
                metadata["model"] = self.model
                metadata["tokens"] = response.usage.input_tokens + response.usage.output_tokens
            except Exception as e:
                response_text = f"Sorry, I encountered an error: {str(e)}"
                metadata["error"] = str(e)
        
        return {
            "response": response_text,
            "metadata": metadata,
            "context": context
        }
    
    def _generate_mock_response(self, message: str, context: Dict[str, Any]) -> str:
        """Generate mock responses for development/testing"""
        message_lower = message.lower()
        
        if "goal" in message_lower:
            if context["goals"]:
                goal = context["goals"][0]
                return f"Great question about your {goal['goal_type']} goal! Based on your recent data, you're making solid progress. Keep focusing on consistency and recovery."
            return "I'd be happy to help you set some fitness goals! What would you like to achieve?"
        
        elif "workout" in message_lower or "training" in message_lower:
            readiness = context.get("readiness")
            if readiness and readiness > 0.7:
                return "Your readiness looks good! You're recovered and ready for a quality training session. Consider a moderate to high-intensity workout today."
            elif readiness and readiness > 0.5:
                return "Your readiness is moderate. Consider a lighter training day focused on technique or an easy aerobic session to continue building fitness."
            elif readiness:
                return "Your metrics suggest you need more recovery. Consider taking it easy today with light movement or rest."
            else:
                return "I don't have enough data yet to assess your readiness. Start tracking your sleep, HRV, and resting heart rate for personalized training recommendations."
        
        elif "sleep" in message_lower or "recovery" in message_lower:
            sleep_data = context["recent_health"].get("sleep", {})
            if sleep_data:
                avg_sleep = sleep_data.get("avg", 0)
                return f"Your average sleep has been {avg_sleep:.1f} hours recently. Aim for 7-9 hours for optimal recovery. Quality sleep is crucial for adaptation and performance."
            return "Sleep is critical for recovery! Aim for 7-9 hours per night. Track your sleep consistently so I can give you better insights."
        
        elif "hrv" in message_lower or "heart rate" in message_lower:
            hrv_data = context["recent_health"].get("hrv", {})
            if hrv_data:
                return f"Your HRV has been averaging {hrv_data['avg']:.1f}ms. HRV is a great indicator of recovery status. Higher values generally indicate better recovery."
            return "HRV (Heart Rate Variability) is a powerful metric for tracking recovery. Make sure you're measuring it consistently each morning."
        
        else:
            return "I'm your AI fitness coach! I can help with workout planning, goal setting, and analyzing your health data. What would you like to know?"

# Global instance
chat_service = AIChatService()
