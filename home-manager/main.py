from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date

app = FastAPI(title="Home Manager API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class Task(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    day: str
    category: str
    priority: Optional[str] = "medium"
    completed: bool = False
    estimated_minutes: Optional[int] = None

class Goal(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    category: str
    target_date: Optional[str] = None
    progress: Optional[int] = 0
    is_active: bool = True

class WeeklyTasks(BaseModel):
    user_id: str
    week_start: Optional[str] = None
    tasks: List[Task]

class DailyTasks(BaseModel):
    user_id: str
    day: str
    tasks: List[Task]

# Tool Model
class Tool(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    category: str  # power_tool, hand_tool, measuring, safety, garden, cleaning
    owned: bool = True
    condition: Optional[str] = "good"  # excellent, good, fair, poor, needs_repair
    storage_location: Optional[str] = None
    purchase_date: Optional[str] = None
    notes: Optional[str] = None

# Material Model
class Material(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    quantity: float = 1.0
    unit: str = "each"  # each, ft, in, sq_ft, gallon, lb, oz, box, bag
    unit_cost: Optional[float] = None
    total_cost: Optional[float] = None
    supplier: Optional[str] = None
    purchased: bool = False
    notes: Optional[str] = None

# Resource Model (documents, guides, videos, contacts)
class Resource(BaseModel):
    id: str
    name: str
    type: str  # document, video, guide, contact, reference, manual, permit
    url: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None

# Project Item - links tools/materials/resources to projects
class ProjectItem(BaseModel):
    item_id: str
    item_type: str  # tool, material, resource
    quantity_needed: Optional[float] = None
    notes: Optional[str] = None

# Project Model
class Project(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    status: str = "planned"  # planned, in_progress, on_hold, completed, cancelled
    category: str  # maintenance, renovation, repair, improvement, outdoor, organization
    priority: Optional[str] = "medium"  # high, medium, low
    start_date: Optional[str] = None
    target_date: Optional[str] = None
    completed_date: Optional[str] = None
    budget: Optional[float] = None
    actual_cost: Optional[float] = None
    tools: List[ProjectItem] = []
    materials: List[ProjectItem] = []
    resources: List[ProjectItem] = []
    tasks: List[str] = []  # List of task IDs
    notes: Optional[str] = None

# Asset Model (home inventory)
class Asset(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    category: str  # appliance, hvac, plumbing, electrical, structural, furniture, outdoor, safety
    location: Optional[str] = None
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    purchase_date: Optional[str] = None
    purchase_price: Optional[float] = None
    warranty_expires: Optional[str] = None
    last_maintenance: Optional[str] = None
    next_maintenance: Optional[str] = None
    condition: Optional[str] = "good"  # excellent, good, fair, poor, needs_repair
    notes: Optional[str] = None

# Response containers
class ToolsResponse(BaseModel):
    user_id: str
    tools: List[Tool]

class MaterialsResponse(BaseModel):
    user_id: str
    materials: List[Material]

class ResourcesResponse(BaseModel):
    user_id: str
    resources: List[Resource]

class ProjectsResponse(BaseModel):
    user_id: str
    projects: List[Project]

class AssetsResponse(BaseModel):
    user_id: str
    assets: List[Asset]

# Default data
def _default_weekly_tasks(user_id: str):
    tasks = [
        {"id": "1", "title": "Laundry", "day": "Monday", "category": "chores", "priority": "high", "completed": False, "estimated_minutes": 60},
        {"id": "2", "title": "Grocery Shopping", "day": "Monday", "category": "errands", "priority": "high", "completed": False, "estimated_minutes": 90},
        {"id": "3", "title": "Vacuum Living Room", "day": "Tuesday", "category": "cleaning", "priority": "medium", "completed": False, "estimated_minutes": 30},
        {"id": "4", "title": "Water Plants", "day": "Tuesday", "category": "maintenance", "priority": "low", "completed": False, "estimated_minutes": 15},
        {"id": "5", "title": "Clean Bathrooms", "day": "Wednesday", "category": "cleaning", "priority": "high", "completed": False, "estimated_minutes": 45},
        {"id": "6", "title": "Meal Prep", "day": "Wednesday", "category": "cooking", "priority": "medium", "completed": False, "estimated_minutes": 120},
        {"id": "7", "title": "Take Out Trash", "day": "Thursday", "category": "chores", "priority": "high", "completed": False, "estimated_minutes": 10},
        {"id": "8", "title": "Organize Pantry", "day": "Thursday", "category": "organizing", "priority": "low", "completed": False, "estimated_minutes": 60},
        {"id": "9", "title": "Mow Lawn", "day": "Friday", "category": "outdoor", "priority": "medium", "completed": False, "estimated_minutes": 90},
        {"id": "10", "title": "Clean Kitchen", "day": "Friday", "category": "cleaning", "priority": "high", "completed": False, "estimated_minutes": 40},
        {"id": "11", "title": "Change Bed Sheets", "day": "Saturday", "category": "chores", "priority": "medium", "completed": False, "estimated_minutes": 20},
        {"id": "12", "title": "Deep Clean Fridge", "day": "Saturday", "category": "cleaning", "priority": "low", "completed": False, "estimated_minutes": 45},
        {"id": "13", "title": "Vacuum Bedrooms", "day": "Sunday", "category": "cleaning", "priority": "medium", "completed": False, "estimated_minutes": 30},
        {"id": "14", "title": "Plan Next Week", "day": "Sunday", "category": "planning", "priority": "high", "completed": False, "estimated_minutes": 30},
    ]
    return {"user_id": user_id, "tasks": tasks}

def _default_goals(user_id: str):
    goals = [
        {
            "id": "g1",
            "title": "Organize Garage",
            "description": "Sort through items, donate unused things, create storage system",
            "category": "organizing",
            "target_date": "2025-12-31",
            "progress": 25,
            "is_active": True
        },
        {
            "id": "g2",
            "title": "Deep Clean All Rooms",
            "description": "Complete deep clean of every room in the house",
            "category": "cleaning",
            "target_date": "2025-12-15",
            "progress": 40,
            "is_active": True
        },
        {
            "id": "g3",
            "title": "Create Meal Planning System",
            "description": "Establish regular meal planning and prep routine",
            "category": "cooking",
            "target_date": "2025-11-30",
            "progress": 60,
            "is_active": True
        },
    ]
    return goals

def _default_tools(user_id: str):
    """Generate default tool inventory"""
    tools = [
        {
            "id": "tool-1",
            "name": "Cordless Drill",
            "description": "18V cordless drill with battery and charger",
            "category": "power_tool",
            "owned": True,
            "condition": "excellent",
            "storage_location": "Garage - Tool Cabinet",
            "purchase_date": "2023-06-15",
            "notes": "DeWalt 20V MAX"
        },
        {
            "id": "tool-2",
            "name": "Hammer",
            "description": "16oz claw hammer",
            "category": "hand_tool",
            "owned": True,
            "condition": "good",
            "storage_location": "Garage - Pegboard",
            "purchase_date": "2020-03-10"
        },
        {
            "id": "tool-3",
            "name": "Tape Measure",
            "description": "25ft tape measure",
            "category": "measuring",
            "owned": True,
            "condition": "good",
            "storage_location": "Garage - Drawer",
            "purchase_date": "2021-01-05"
        },
        {
            "id": "tool-4",
            "name": "Safety Glasses",
            "description": "Impact-resistant safety glasses",
            "category": "safety",
            "owned": True,
            "condition": "good",
            "storage_location": "Garage - Tool Cabinet"
        },
        {
            "id": "tool-5",
            "name": "Circular Saw",
            "description": "7-1/4 inch circular saw",
            "category": "power_tool",
            "owned": True,
            "condition": "good",
            "storage_location": "Garage - Shelf",
            "purchase_date": "2022-09-20"
        },
        {
            "id": "tool-6",
            "name": "Screwdriver Set",
            "description": "Phillips and flathead set, various sizes",
            "category": "hand_tool",
            "owned": True,
            "condition": "excellent",
            "storage_location": "Garage - Drawer"
        },
        {
            "id": "tool-7",
            "name": "Level",
            "description": "24-inch spirit level",
            "category": "measuring",
            "owned": True,
            "condition": "good",
            "storage_location": "Garage - Pegboard"
        },
        {
            "id": "tool-8",
            "name": "Lawn Mower",
            "description": "21-inch self-propelled gas mower",
            "category": "garden",
            "owned": True,
            "condition": "good",
            "storage_location": "Garage - Floor",
            "purchase_date": "2021-04-01",
            "notes": "Honda HRX217"
        },
    ]
    return tools

def _default_materials(user_id: str):
    """Generate default materials list"""
    materials = [
        {
            "id": "mat-1",
            "name": "2x4 Lumber (8ft)",
            "description": "Kiln-dried whitewood studs",
            "quantity": 10,
            "unit": "each",
            "unit_cost": 5.98,
            "total_cost": 59.80,
            "supplier": "Home Depot",
            "purchased": True,
            "notes": "For garage shelf project"
        },
        {
            "id": "mat-2",
            "name": "Wood Screws (2.5in)",
            "description": "#8 wood screws, box of 100",
            "quantity": 2,
            "unit": "box",
            "unit_cost": 8.99,
            "total_cost": 17.98,
            "supplier": "Home Depot",
            "purchased": True
        },
        {
            "id": "mat-3",
            "name": "Interior Paint (White)",
            "description": "Semi-gloss interior latex paint",
            "quantity": 2,
            "unit": "gallon",
            "unit_cost": 35.00,
            "total_cost": 70.00,
            "supplier": "Sherwin Williams",
            "purchased": False,
            "notes": "For bathroom refresh"
        },
        {
            "id": "mat-4",
            "name": "Paint Brushes",
            "description": "2-inch angled brushes for trim",
            "quantity": 3,
            "unit": "each",
            "unit_cost": 12.99,
            "supplier": "Home Depot",
            "purchased": False
        },
        {
            "id": "mat-5",
            "name": "Plywood (3/4in)",
            "description": "4x8 sheet sanded plywood",
            "quantity": 2,
            "unit": "each",
            "unit_cost": 45.00,
            "total_cost": 90.00,
            "supplier": "Lowes",
            "purchased": False,
            "notes": "For garage shelving"
        },
    ]
    return materials

def _default_resources(user_id: str):
    """Generate default resources list"""
    resources = [
        {
            "id": "res-1",
            "name": "DIY Garage Shelving Guide",
            "type": "guide",
            "url": "https://example.com/garage-shelving",
            "description": "Step-by-step guide for building garage storage shelves",
            "notes": "Good reference for shelf project"
        },
        {
            "id": "res-2",
            "name": "HVAC Filter Replacement Video",
            "type": "video",
            "url": "https://youtube.com/example",
            "description": "Tutorial on replacing HVAC filters"
        },
        {
            "id": "res-3",
            "name": "Home Warranty Documentation",
            "type": "document",
            "description": "Home warranty policy and claim procedures",
            "notes": "Expires December 2026"
        },
        {
            "id": "res-4",
            "name": "Licensed Electrician - John Smith",
            "type": "contact",
            "description": "Recommended electrician for major electrical work",
            "notes": "Phone: 555-0123, used for panel upgrade"
        },
        {
            "id": "res-5",
            "name": "Appliance Manuals",
            "type": "manual",
            "description": "Collection of appliance user manuals",
            "notes": "Stored in filing cabinet"
        },
    ]
    return resources

def _default_projects(user_id: str):
    """Generate default projects list"""
    projects = [
        {
            "id": "proj-1",
            "title": "Garage Storage Shelves",
            "description": "Build sturdy shelving units along garage walls for storage",
            "status": "in_progress",
            "category": "improvement",
            "priority": "high",
            "start_date": "2026-01-15",
            "target_date": "2026-02-15",
            "budget": 300.00,
            "actual_cost": 167.78,
            "tools": [
                {"item_id": "tool-1", "item_type": "tool", "notes": "For drilling pilot holes"},
                {"item_id": "tool-5", "item_type": "tool", "notes": "For cutting plywood"},
                {"item_id": "tool-3", "item_type": "tool"},
                {"item_id": "tool-7", "item_type": "tool"},
            ],
            "materials": [
                {"item_id": "mat-1", "item_type": "material", "quantity_needed": 10},
                {"item_id": "mat-2", "item_type": "material", "quantity_needed": 2},
                {"item_id": "mat-5", "item_type": "material", "quantity_needed": 2},
            ],
            "resources": [
                {"item_id": "res-1", "item_type": "resource"},
            ],
            "tasks": [],
            "notes": "Need to clear out garage first"
        },
        {
            "id": "proj-2",
            "title": "Bathroom Paint Refresh",
            "description": "Repaint master bathroom walls and trim",
            "status": "planned",
            "category": "renovation",
            "priority": "medium",
            "target_date": "2026-03-01",
            "budget": 150.00,
            "tools": [
                {"item_id": "tool-3", "item_type": "tool"},
            ],
            "materials": [
                {"item_id": "mat-3", "item_type": "material", "quantity_needed": 2},
                {"item_id": "mat-4", "item_type": "material", "quantity_needed": 3},
            ],
            "resources": [],
            "tasks": [],
            "notes": "Need to pick paint colors"
        },
        {
            "id": "proj-3",
            "title": "HVAC Annual Maintenance",
            "description": "Replace filters and schedule professional inspection",
            "status": "planned",
            "category": "maintenance",
            "priority": "high",
            "target_date": "2026-02-01",
            "budget": 200.00,
            "tools": [],
            "materials": [],
            "resources": [
                {"item_id": "res-2", "item_type": "resource"},
            ],
            "tasks": [],
            "notes": "Schedule with HVAC company"
        },
    ]
    return projects

def _default_assets(user_id: str):
    """Generate default home assets inventory"""
    assets = [
        {
            "id": "asset-1",
            "name": "Refrigerator",
            "description": "French door refrigerator with ice maker",
            "category": "appliance",
            "location": "Kitchen",
            "manufacturer": "Samsung",
            "model_number": "RF28R7551SR",
            "purchase_date": "2022-03-15",
            "purchase_price": 2499.00,
            "warranty_expires": "2027-03-15",
            "condition": "excellent",
            "notes": "Extended warranty purchased"
        },
        {
            "id": "asset-2",
            "name": "HVAC System",
            "description": "Central air conditioning and heating",
            "category": "hvac",
            "location": "Utility Room",
            "manufacturer": "Carrier",
            "model_number": "24ACC636A003",
            "purchase_date": "2020-07-01",
            "warranty_expires": "2030-07-01",
            "last_maintenance": "2025-10-15",
            "next_maintenance": "2026-04-15",
            "condition": "good",
            "notes": "Bi-annual maintenance schedule"
        },
        {
            "id": "asset-3",
            "name": "Water Heater",
            "description": "50-gallon gas water heater",
            "category": "plumbing",
            "location": "Garage",
            "manufacturer": "Rheem",
            "model_number": "XG50T06EC36U1",
            "purchase_date": "2019-05-20",
            "purchase_price": 850.00,
            "warranty_expires": "2025-05-20",
            "condition": "good",
            "notes": "Consider replacement in next 2 years"
        },
        {
            "id": "asset-4",
            "name": "Washer",
            "description": "Front-load washing machine",
            "category": "appliance",
            "location": "Laundry Room",
            "manufacturer": "LG",
            "model_number": "WM4000HWA",
            "purchase_date": "2023-01-10",
            "purchase_price": 899.00,
            "warranty_expires": "2024-01-10",
            "condition": "excellent"
        },
        {
            "id": "asset-5",
            "name": "Dryer",
            "description": "Electric dryer with steam",
            "category": "appliance",
            "location": "Laundry Room",
            "manufacturer": "LG",
            "model_number": "DLEX4000W",
            "purchase_date": "2023-01-10",
            "purchase_price": 799.00,
            "warranty_expires": "2024-01-10",
            "condition": "excellent"
        },
        {
            "id": "asset-6",
            "name": "Electrical Panel",
            "description": "200 amp main breaker panel",
            "category": "electrical",
            "location": "Garage",
            "manufacturer": "Square D",
            "model_number": "HOM2040M200PC",
            "purchase_date": "2018-06-01",
            "condition": "good",
            "notes": "Upgraded from 100 amp in 2018"
        },
        {
            "id": "asset-7",
            "name": "Garage Door Opener",
            "description": "Belt-drive garage door opener",
            "category": "outdoor",
            "location": "Garage",
            "manufacturer": "Chamberlain",
            "model_number": "B6765",
            "purchase_date": "2021-08-15",
            "warranty_expires": "2026-08-15",
            "condition": "good"
        },
        {
            "id": "asset-8",
            "name": "Smoke Detectors",
            "description": "Hardwired smoke/CO detectors (set of 6)",
            "category": "safety",
            "location": "Throughout home",
            "manufacturer": "First Alert",
            "model_number": "SC9120B",
            "purchase_date": "2022-01-01",
            "next_maintenance": "2026-06-01",
            "condition": "good",
            "notes": "Replace batteries annually, replace units by 2032"
        },
    ]
    return assets

def _day_name_from_date_str(date_str: Optional[str]) -> str:
    if date_str:
        try:
            d = datetime.fromisoformat(date_str).date()
        except Exception:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                d = date.today()
    else:
        d = date.today()
    return d.strftime("%A")

# Endpoints
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ready")
async def ready():
    return {"status": "ready"}

@app.get("/tasks/weekly/{user_id}")
async def get_weekly_tasks(user_id: str, week_start: Optional[str] = None):
    """Get all tasks for the week"""
    data = _default_weekly_tasks(user_id)
    if week_start:
        data["week_start"] = week_start
    return data

@app.get("/tasks/today/{user_id}")
async def get_today_tasks(user_id: str, date: Optional[str] = None):
    """Get tasks for today (or specified date)"""
    day_name = _day_name_from_date_str(date)
    all_tasks = _default_weekly_tasks(user_id)

    today_tasks = [task for task in all_tasks["tasks"] if task.get("day") == day_name]
    return {"user_id": user_id, "day": day_name, "tasks": today_tasks}

@app.get("/tasks/category/{user_id}/{category}")
async def get_tasks_by_category(user_id: str, category: str):
    """Get all tasks in a specific category"""
    all_tasks = _default_weekly_tasks(user_id)
    filtered = [task for task in all_tasks["tasks"] if task.get("category") == category]
    return {"user_id": user_id, "category": category, "tasks": filtered}

@app.get("/goals/{user_id}")
async def get_goals(user_id: str):
    """Get all goals for user"""
    goals = _default_goals(user_id)
    return {"user_id": user_id, "goals": goals}

@app.get("/stats/{user_id}")
async def get_stats(user_id: str):
    """Get statistics for user"""
    all_tasks = _default_weekly_tasks(user_id)
    total_tasks = len(all_tasks["tasks"])
    completed_tasks = sum(1 for t in all_tasks["tasks"] if t.get("completed", False))
    total_minutes = sum(t.get("estimated_minutes", 0) for t in all_tasks["tasks"])

    goals = _default_goals(user_id)
    active_goals = sum(1 for g in goals if g.get("is_active", True))
    avg_progress = sum(g.get("progress", 0) for g in goals) / len(goals) if goals else 0

    return {
        "user_id": user_id,
        "tasks": {
            "total": total_tasks,
            "completed": completed_tasks,
            "completion_rate": round(completed_tasks / total_tasks * 100, 1) if total_tasks > 0 else 0,
            "total_estimated_minutes": total_minutes
        },
        "goals": {
            "total": len(goals),
            "active": active_goals,
            "average_progress": round(avg_progress, 1)
        }
    }

# ============== TOOL ENDPOINTS ==============

@app.get("/tools/{user_id}")
async def get_tools(user_id: str):
    """Get all tools for user"""
    tools = _default_tools(user_id)
    return {"user_id": user_id, "tools": tools}

@app.get("/tools/{user_id}/item/{tool_id}")
async def get_tool_by_id(user_id: str, tool_id: str):
    """Get a specific tool by ID"""
    tools = _default_tools(user_id)
    tool = next((t for t in tools if t["id"] == tool_id), None)
    if tool:
        return {"user_id": user_id, "tool": tool}
    return {"user_id": user_id, "tool": None, "error": "Tool not found"}

@app.get("/tools/{user_id}/category/{category}")
async def get_tools_by_category(user_id: str, category: str):
    """Get tools filtered by category"""
    tools = _default_tools(user_id)
    filtered = [t for t in tools if t.get("category") == category]
    return {"user_id": user_id, "category": category, "tools": filtered}

@app.get("/tools/{user_id}/owned")
async def get_owned_tools(user_id: str, owned: bool = True):
    """Get tools filtered by ownership status"""
    tools = _default_tools(user_id)
    filtered = [t for t in tools if t.get("owned", True) == owned]
    return {"user_id": user_id, "owned": owned, "tools": filtered}

# ============== MATERIAL ENDPOINTS ==============

@app.get("/materials/{user_id}")
async def get_materials(user_id: str):
    """Get all materials for user"""
    materials = _default_materials(user_id)
    return {"user_id": user_id, "materials": materials}

@app.get("/materials/{user_id}/item/{material_id}")
async def get_material_by_id(user_id: str, material_id: str):
    """Get a specific material by ID"""
    materials = _default_materials(user_id)
    material = next((m for m in materials if m["id"] == material_id), None)
    if material:
        return {"user_id": user_id, "material": material}
    return {"user_id": user_id, "material": None, "error": "Material not found"}

@app.get("/materials/{user_id}/purchased/{purchased}")
async def get_materials_by_purchased(user_id: str, purchased: bool):
    """Get materials filtered by purchase status"""
    materials = _default_materials(user_id)
    filtered = [m for m in materials if m.get("purchased", False) == purchased]
    return {"user_id": user_id, "purchased": purchased, "materials": filtered}

@app.get("/materials/{user_id}/supplier/{supplier}")
async def get_materials_by_supplier(user_id: str, supplier: str):
    """Get materials filtered by supplier"""
    materials = _default_materials(user_id)
    filtered = [m for m in materials if m.get("supplier", "").lower() == supplier.lower()]
    return {"user_id": user_id, "supplier": supplier, "materials": filtered}

# ============== RESOURCE ENDPOINTS ==============

@app.get("/resources/{user_id}")
async def get_resources(user_id: str):
    """Get all resources for user"""
    resources = _default_resources(user_id)
    return {"user_id": user_id, "resources": resources}

@app.get("/resources/{user_id}/item/{resource_id}")
async def get_resource_by_id(user_id: str, resource_id: str):
    """Get a specific resource by ID"""
    resources = _default_resources(user_id)
    resource = next((r for r in resources if r["id"] == resource_id), None)
    if resource:
        return {"user_id": user_id, "resource": resource}
    return {"user_id": user_id, "resource": None, "error": "Resource not found"}

@app.get("/resources/{user_id}/type/{resource_type}")
async def get_resources_by_type(user_id: str, resource_type: str):
    """Get resources filtered by type"""
    resources = _default_resources(user_id)
    filtered = [r for r in resources if r.get("type") == resource_type]
    return {"user_id": user_id, "type": resource_type, "resources": filtered}

# ============== PROJECT ENDPOINTS ==============

@app.get("/projects/{user_id}")
async def get_projects(user_id: str):
    """Get all projects for user"""
    projects = _default_projects(user_id)
    return {"user_id": user_id, "projects": projects}

@app.get("/projects/{user_id}/item/{project_id}")
async def get_project_by_id(user_id: str, project_id: str):
    """Get a specific project by ID with resolved tools, materials, and resources"""
    projects = _default_projects(user_id)
    project = next((p for p in projects if p["id"] == project_id), None)
    if project:
        # Resolve tool, material, and resource references
        tools = _default_tools(user_id)
        materials = _default_materials(user_id)
        resources = _default_resources(user_id)

        resolved_tools = []
        for item in project.get("tools", []):
            tool = next((t for t in tools if t["id"] == item["item_id"]), None)
            if tool:
                resolved_tools.append({**tool, "project_notes": item.get("notes")})

        resolved_materials = []
        for item in project.get("materials", []):
            material = next((m for m in materials if m["id"] == item["item_id"]), None)
            if material:
                resolved_materials.append({
                    **material,
                    "quantity_needed": item.get("quantity_needed"),
                    "project_notes": item.get("notes")
                })

        resolved_resources = []
        for item in project.get("resources", []):
            resource = next((r for r in resources if r["id"] == item["item_id"]), None)
            if resource:
                resolved_resources.append({**resource, "project_notes": item.get("notes")})

        return {
            "user_id": user_id,
            "project": project,
            "resolved_tools": resolved_tools,
            "resolved_materials": resolved_materials,
            "resolved_resources": resolved_resources
        }
    return {"user_id": user_id, "project": None, "error": "Project not found"}

@app.get("/projects/{user_id}/status/{status}")
async def get_projects_by_status(user_id: str, status: str):
    """Get projects filtered by status"""
    projects = _default_projects(user_id)
    filtered = [p for p in projects if p.get("status") == status]
    return {"user_id": user_id, "status": status, "projects": filtered}

@app.get("/projects/{user_id}/category/{category}")
async def get_projects_by_category(user_id: str, category: str):
    """Get projects filtered by category"""
    projects = _default_projects(user_id)
    filtered = [p for p in projects if p.get("category") == category]
    return {"user_id": user_id, "category": category, "projects": filtered}

# ============== ASSET ENDPOINTS ==============

@app.get("/assets/{user_id}")
async def get_assets(user_id: str):
    """Get all home assets for user"""
    assets = _default_assets(user_id)
    return {"user_id": user_id, "assets": assets}

@app.get("/assets/{user_id}/item/{asset_id}")
async def get_asset_by_id(user_id: str, asset_id: str):
    """Get a specific asset by ID"""
    assets = _default_assets(user_id)
    asset = next((a for a in assets if a["id"] == asset_id), None)
    if asset:
        return {"user_id": user_id, "asset": asset}
    return {"user_id": user_id, "asset": None, "error": "Asset not found"}

@app.get("/assets/{user_id}/category/{category}")
async def get_assets_by_category(user_id: str, category: str):
    """Get assets filtered by category"""
    assets = _default_assets(user_id)
    filtered = [a for a in assets if a.get("category") == category]
    return {"user_id": user_id, "category": category, "assets": filtered}

@app.get("/assets/{user_id}/location/{location}")
async def get_assets_by_location(user_id: str, location: str):
    """Get assets filtered by location"""
    assets = _default_assets(user_id)
    filtered = [a for a in assets if location.lower() in a.get("location", "").lower()]
    return {"user_id": user_id, "location": location, "assets": filtered}

@app.get("/assets/{user_id}/maintenance-due")
async def get_assets_needing_maintenance(user_id: str):
    """Get assets with upcoming or overdue maintenance"""
    assets = _default_assets(user_id)
    today = date.today().isoformat()
    filtered = [
        a for a in assets
        if a.get("next_maintenance") and a.get("next_maintenance") <= today
    ]
    return {"user_id": user_id, "assets": filtered}

@app.get("/assets/{user_id}/warranty-expiring")
async def get_assets_warranty_expiring(user_id: str, days: int = 90):
    """Get assets with warranties expiring within specified days"""
    from datetime import timedelta
    assets = _default_assets(user_id)
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    today = date.today().isoformat()
    filtered = [
        a for a in assets
        if a.get("warranty_expires") and today <= a.get("warranty_expires") <= cutoff
    ]
    return {"user_id": user_id, "days": days, "assets": filtered}
