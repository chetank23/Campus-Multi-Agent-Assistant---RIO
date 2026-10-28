import time
from typing import List, Dict, Tuple, Optional, Any
from collections import defaultdict
from pydantic import BaseModel
from ortools.sat.python import cp_model
from backend.schemas.timetable_generation import OptimizerInput, TimetableEntryResult

class SolverResult(BaseModel):
    feasible: bool
    status: str
    message: str
    entries: List[TimetableEntryResult] = []
    solve_time_seconds: float = 0.0
    diagnostics: List[str] = []

class TimetableSolver:
    def __init__(self, opt_input: OptimizerInput, time_limit: int = 60, strategy: str = "BALANCED", previous_entries: Optional[List[Any]] = None, locked_assignments: Optional[List[Any]] = None, disrupted_assignments: Optional[List[Any]] = None, allow_ripple: bool = False, perturbation_penalty_slot: int = 500, perturbation_penalty_room: int = 200):
        self.previous_entries = previous_entries or []
        self.locked_assignments = locked_assignments or []
        self.disrupted_assignments = disrupted_assignments or []
        self.allow_ripple = allow_ripple
        self.perturbation_penalty_slot = perturbation_penalty_slot
        self.perturbation_penalty_room = perturbation_penalty_room
        self.input = opt_input
        self.time_limit = time_limit
        self.strategy = (strategy or "BALANCED").upper()
        self.model = cp_model.CpModel()
        self.x = {}  # decision variables
        
        # Precompute maps for faster lookup
        self.courses = {c.id: c for c in opt_input.courses}
        self.sections = {s.id: s for s in opt_input.sections}
        self.batches = {b.id: b for b in opt_input.batches}
        self.rooms = {r.id: r for r in opt_input.rooms}
        self.labs = {l.room_id: l for l in opt_input.labs}
        self.faculty = {f.id: f for f in opt_input.faculty}
        self.slots = {t.id: t for t in opt_input.time_slots}
        
        self.faculty_availability = defaultdict(dict)
        for fa in opt_input.faculty_availability:
            self.faculty_availability[fa.faculty_id][fa.slot_id] = fa

        # Map assignment to its attributes
        self.assignments = opt_input.course_assignments
        
        # Global calendar: slots that fall on holidays are technically excluded, 
        # but time_slots usually already represent valid working slots. 
        # The prompt says "No class on holiday/exam calendar dates". If time_slots 
        # don't have dates, we assume time_slots are a generic weekly template. 
        # In a real system, the weekly template maps to dates. We will assume all passed 
        # time_slots are valid for the weekly schedule unless excluded.

    def _get_eligible_rooms(self, assignment, hour_type: str) -> List[int]:
        course = self.courses[assignment.course_id]
        section_id = assignment.section_id
        
        student_count = 0
        if section_id:
            student_count = self.sections[section_id].student_count
        elif assignment.batch_id:
            student_count = self.batches[assignment.batch_id].student_count

        eligible = []
        for r_id, room in self.rooms.items():
            if room.capacity < student_count:
                continue
                
            if hour_type == 'PRACTICAL':
                if room.room_type == 'LAB' and r_id in self.labs:
                    eligible.append(r_id)
            else:
                if room.room_type in ('CLASSROOM', 'SEMINAR_HALL', 'AUDITORIUM'):
                    eligible.append(r_id)
        return eligible

    def _get_eligible_slots(self, faculty_id: int) -> List[int]:
        # Filter slots by faculty availability and exclude BREAK/LUNCH periods
        eligible = []
        for t_id, slot in self.slots.items():
            if getattr(slot, "slot_type", "") in ("BREAK", "LUNCH"):
                continue
            fa = self.faculty_availability[faculty_id].get(t_id)
            if fa and fa.availability == 'UNAVAILABLE':
                continue
            eligible.append(t_id)
        return eligible

    def build_model(self):
        # 1. Create Decision Variables
        # x[a_id, h_type, r_id, t_id] = 1 if assignment a's hour_type is scheduled in room r at time t
        
        # To handle multiple hours of the same type (e.g. 3 lecture hours), 
        # we don't need a separate variable for each hour instance. We just need the SUM of x across r, t 
        # to equal the required hours! 
        # Wait, if x is boolean, sum(x) = 3 means exactly 3 distinct (room, slot) combinations are chosen.
        # This prevents 2 classes of the same assignment in the same slot automatically because x is boolean!
        
        a_r_t_vars = defaultdict(list)
        f_t_vars = defaultdict(list)
        s_t_vars = defaultdict(list)
        b_t_vars = defaultdict(list)
        r_t_vars = defaultdict(list)
        
        self.assignment_vars = []
        
        for a in self.assignments:
            course = self.courses[a.course_id]
            f_id = a.faculty_id
            sec_id = a.section_id
            batch_id = a.batch_id
            
            hours_needed = {
                'THEORY': course.lecture_hours + course.tutorial_hours,
                'PRACTICAL': course.practical_hours
            }
            
            for h_type, req_hours in hours_needed.items():
                if req_hours <= 0:
                    continue
                    
                eligible_rooms = self._get_eligible_rooms(a, h_type)
                eligible_slots = self._get_eligible_slots(f_id)
                
                # Check for obvious infeasibility
                if not eligible_rooms:
                    return False, f"No eligible rooms for {h_type} of course {course.id}"
                if len(eligible_slots) < req_hours:
                    return False, f"Not enough available slots for faculty {f_id} teaching {course.id}"
                
                var_list = []
                for r_id in eligible_rooms:
                    for t_id in eligible_slots:
                        var_name = f"x_a{a.id}_{h_type}_r{r_id}_t{t_id}"
                        v = self.model.new_bool_var(var_name)
                        self.x[(a.id, h_type, r_id, t_id)] = v
                        var_list.append(v)
                        
                        a_r_t_vars[(a.id, h_type)].append(v)
                        f_t_vars[(f_id, t_id)].append(v)
                        if sec_id:
                            s_t_vars[(sec_id, t_id)].append(v)
                        if batch_id:
                            b_t_vars[(batch_id, t_id)].append(v)
                        elif sec_id:
                            for b in self.batches.values():
                                if b.section_id == sec_id:
                                    b_t_vars[(b.id, t_id)].append(v)
                        r_t_vars[(r_id, t_id)].append(v)
                
                self.assignment_vars.append((a, h_type, req_hours, var_list))
                
        # 2. Hard Constraints
        
        # A. Required Course Hours
        for a, h_type, req_hours, var_list in self.assignment_vars:
            self.model.add_exactly_one(var_list) if req_hours == 1 else self.model.add(sum(var_list) == req_hours)
            
        # B. Faculty Conflict (<= 1 per slot)
        for (f_id, t_id), vars_in_slot in f_t_vars.items():
            if len(vars_in_slot) > 1:
                self.model.add_at_most_one(vars_in_slot)
                
        # C. Section Conflict (<= 1 per slot)
        for (sec_id, t_id), vars_in_slot in s_t_vars.items():
            if len(vars_in_slot) > 1:
                self.model.add_at_most_one(vars_in_slot)

        # C2. Batch Conflict (<= 1 per slot)
        for (b_id, t_id), vars_in_slot in b_t_vars.items():
            if len(vars_in_slot) > 1:
                self.model.add_at_most_one(vars_in_slot)
                
        # D. Room Conflict (<= 1 per slot)
        for (r_id, t_id), vars_in_slot in r_t_vars.items():
            if len(vars_in_slot) > 1:
                self.model.add_at_most_one(vars_in_slot)

        # Overlapping interval constraints (for slots with different IDs that overlap in time)
        slot_list = list(self.slots.values())
        for i in range(len(slot_list)):
            for j in range(i + 1, len(slot_list)):
                sl1 = slot_list[i]
                sl2 = slot_list[j]
                if sl1.day == sl2.day and sl1.start_time and sl1.end_time and sl2.start_time and sl2.end_time:
                    if max(sl1.start_time, sl2.start_time) < min(sl1.end_time, sl2.end_time):
                        for f_id in self.faculty.keys():
                            v1 = f_t_vars.get((f_id, sl1.id), [])
                            v2 = f_t_vars.get((f_id, sl2.id), [])
                            if v1 and v2:
                                self.model.add_at_most_one(v1 + v2)
                        for r_id in self.rooms.keys():
                            v1 = r_t_vars.get((r_id, sl1.id), [])
                            v2 = r_t_vars.get((r_id, sl2.id), [])
                            if v1 and v2:
                                self.model.add_at_most_one(v1 + v2)
                        for sec_id in self.sections.keys():
                            v1 = s_t_vars.get((sec_id, sl1.id), [])
                            v2 = s_t_vars.get((sec_id, sl2.id), [])
                            if v1 and v2:
                                self.model.add_at_most_one(v1 + v2)
                        for b_id in self.batches.keys():
                            v1 = b_t_vars.get((b_id, sl1.id), [])
                            v2 = b_t_vars.get((b_id, sl2.id), [])
                            if v1 and v2:
                                self.model.add_at_most_one(v1 + v2)
                
        # E. Elective Group Conflict (<= 1 course per elective group per slot per section)
        # Note: We group assignments by (elective_group, section, slot)
        for eg in self.input.elective_groups:
            eg_course_ids = [egc.course_id for egc in self.input.elective_group_courses if egc.group_id == eg.id]
            if not eg_course_ids:
                continue
                
            eg_s_t_vars = defaultdict(list)
            
            for (a_id, h_type, r_id, t_id), v in self.x.items():
                a = next(ast for ast in self.assignments if ast.id == a_id)
                if a.course_id in eg_course_ids:
                    # If assignment has a specific section, it belongs to that section.
                    # If it has NO section (None), it applies to ALL sections in the semester for this elective group.
                    # To model this, we just use the section_id as the key.
                    # Wait, if a.section_id is None, it means the whole group takes it. 
                    # If we just group by section_id, the None section won't conflict with specific sections!
                    # Actually, if we group by `(a.section_id, t_id)`, it protects specific sections.
                    # Since Elective Groups are usually bound to a Semester/Department, and Open Electives (section=None) apply to all,
                    # we should probably add `v` to EVERY section's bucket if `section_id` is None.
                    if a.section_id is not None:
                        eg_s_t_vars[(a.section_id, t_id)].append(v)
                    else:
                        # Applies to all sections that we are tracking
                        for sec_id in self.sections.keys():
                            eg_s_t_vars[(sec_id, t_id)].append(v)
                            
            for (sec_id, t_id), vars_in_slot in eg_s_t_vars.items():
                if len(vars_in_slot) > 1:
                    self.model.add_at_most_one(vars_in_slot)
                
        # F. Minimal-Perturbation Constraints (Locked and Disrupted assignments)
        if self.locked_assignments:
            for item in self.locked_assignments:
                if isinstance(item, tuple):
                    a_id, h_type, r_id, t_id = item
                elif isinstance(item, dict):
                    a_id, h_type, r_id, t_id = item["course_assignment_id"], item["hour_type"], item["room_id"], item["slot_id"]
                else:
                    a_id, h_type, r_id, t_id = item.course_assignment_id, item.hour_type, item.room_id, item.slot_id
                key = (a_id, h_type, r_id, t_id)
                if key in self.x:
                    self.model.add(self.x[key] == 1)
                else:
                    return False, f"Locked assignment #{a_id} ({h_type}) in room #{r_id} at slot #{t_id} cannot be satisfied under current constraints."

        if self.disrupted_assignments:
            for item in self.disrupted_assignments:
                if isinstance(item, tuple):
                    a_id, h_type, r_id, t_id = item
                elif isinstance(item, dict):
                    a_id, h_type, r_id, t_id = item["course_assignment_id"], item["hour_type"], item["room_id"], item["slot_id"]
                else:
                    a_id, h_type, r_id, t_id = item.course_assignment_id, item.hour_type, item.room_id, item.slot_id
                key = (a_id, h_type, r_id, t_id)
                if key in self.x:
                    self.model.add(self.x[key] == 0)

        self._build_soft_constraints()
            
        return True, "Model built successfully"


    def _build_soft_constraints(self):
        # Base weights for BALANCED
        W_FACULTY_GAP = 10
        W_STUDENT_GAP = 10
        W_PREFERRED_SLOT = 5
        W_ROOM_CHANGE = 5
        W_LATE_LAB = 5
        W_WORKLOAD_BALANCE = 10

        # Optimization profiles modify soft-objective penalties/bonuses without touching hard constraints
        if self.strategy == "FACULTY_COMFORT":
            W_FACULTY_GAP = 30
            W_WORKLOAD_BALANCE = 25
            W_PREFERRED_SLOT = 15
            W_ROOM_CHANGE = 2
            W_LATE_LAB = 5
        elif self.strategy == "ROOM_EFFICIENCY":
            W_ROOM_CHANGE = 25
            W_STUDENT_GAP = 15
            W_FACULTY_GAP = 5
            W_WORKLOAD_BALANCE = 5
            W_PREFERRED_SLOT = 5
        elif self.strategy == "LAB_PREFERENCE":
            W_LATE_LAB = 30
            W_STUDENT_GAP = 10
            W_FACULTY_GAP = 10
            W_PREFERRED_SLOT = 5
            W_ROOM_CHANGE = 5

        objective_terms = []


        # 1. Preferred Slot Bonus (maximize preference -> minimize -1 * preference)
        # 2. Late Lab Penalty
        for (a_id, h_type, r_id, t_id), v in self.x.items():
            a = next(ast for ast in self.assignments if ast.id == a_id)
            
            # Preferred Slot
            fa = self.faculty_availability[a.faculty_id].get(t_id)
            if fa and fa.availability == 'PREFERRED':
                pref = fa.preference if fa.preference > 0 else 1
                objective_terms.append(v * (-1 * W_PREFERRED_SLOT * pref))
                
            # Late Lab
            c = self.courses.get(a.course_id)
            t = self.slots.get(t_id)
            if c and (c.requires_lab or c.course_type == 'LAB') and t:
                # Late lab: starts at or after 14:00 (2:00 PM)
                if t.start_time and t.start_time.hour >= 14:
                    objective_terms.append(v * W_LATE_LAB)

        # Helper to get day groups
        slots_by_day = {}
        for t_id, slot in self.slots.items():
            if slot.day not in slots_by_day:
                slots_by_day[slot.day] = []
            slots_by_day[slot.day].append(t_id)

        # 3. Faculty Gap Penalty & 6. Workload Variance (min-max daily workload)
        # For each faculty and each day, compute first and last teaching slots, and total slots.
        for f_id in self.faculty.keys():
            daily_workloads = []
            for day, t_ids in slots_by_day.items():
                day_t_ids = sorted(t_ids) # assume ID sorts by time logically, or we could sort by start_time
                
                # faculty teaching in this slot
                f_teaching_slots = []
                for t_id in day_t_ids:
                    # Sum of x for all assignments of this faculty at this t_id
                    v_list = [v for (a_id, h_type, r_id, t), v in self.x.items() 
                              if t == t_id and next(a for a in self.assignments if a.id == a_id).faculty_id == f_id]
                    if v_list:
                        # Faculty is teaching if sum(v_list) > 0
                        is_teaching = self.model.new_bool_var(f"f_{f_id}_{day}_{t_id}_teaching")
                        # Add constraint: is_teaching == 1 iff sum(v_list) == 1
                        # Since constraints say faculty can teach at most 1 class per slot, sum is 0 or 1.
                        self.model.add(sum(v_list) == is_teaching)
                        f_teaching_slots.append((t_id, is_teaching))
                
                if not f_teaching_slots:
                    continue
                    
                total_teaching = sum(var for _, var in f_teaching_slots)
                daily_workloads.append(total_teaching)
                
                # Active day boolean
                is_active_day = self.model.new_bool_var(f"f_{f_id}_{day}_active")
                self.model.add_max_equality(is_active_day, [var for _, var in f_teaching_slots])
                
                # Find min and max active slot indices
                # Let's map t_id to an index 0, 1, 2... for the day
                first_slot_idx = self.model.new_int_var(0, len(day_t_ids), f"f_{f_id}_{day}_first")
                last_slot_idx = self.model.new_int_var(0, len(day_t_ids), f"f_{f_id}_{day}_last")
                
                # If not active, we want first_slot_idx = 0 and last_slot_idx = 0.
                # If active, first_slot_idx = min(i where is_teaching[i] == 1)
                
                for i, (t_id, var) in enumerate(f_teaching_slots):
                    # if var == 1, then first_slot_idx <= i, last_slot_idx >= i
                    self.model.add(first_slot_idx <= i).only_enforce_if(var)
                    self.model.add(last_slot_idx >= i).only_enforce_if(var)
                
                # To prevent gaps from being falsely minimized when active by pushing first up and last down,
                # CP-SAT minimizes the objective, so the gap will naturally shrink to its valid boundary.
                # However, if is_active_day == 0, we must force them to 0 so gap is 0.
                self.model.add(first_slot_idx == 0).only_enforce_if(is_active_day.Not())
                self.model.add(last_slot_idx == 0).only_enforce_if(is_active_day.Not())
                
                # Also, when active, gap = (last - first + 1) - total
                # To avoid (0 - 0 + 1) = 1 when inactive, we multiply the +1 by is_active_day.
                gap_expr = last_slot_idx - first_slot_idx + is_active_day - total_teaching
                
                gap_var = self.model.new_int_var(0, len(day_t_ids), f"f_{f_id}_{day}_gap")
                self.model.add(gap_var == gap_expr)
                
                objective_terms.append(gap_var * W_FACULTY_GAP)
            
            if daily_workloads:
                max_workload = self.model.new_int_var(0, 100, f"f_{f_id}_max_w")
                min_workload = self.model.new_int_var(0, 100, f"f_{f_id}_min_w")
                self.model.add_max_equality(max_workload, daily_workloads)
                self.model.add_min_equality(min_workload, daily_workloads)
                objective_terms.append((max_workload - min_workload) * W_WORKLOAD_BALANCE)

        # 4. Student Gap Penalty & 5. Unnecessary Room Change Penalty
        for s_id in self.sections.keys():
            for day, t_ids in slots_by_day.items():
                day_t_ids = sorted(t_ids)
                
                # student teaching in this slot
                s_teaching_slots = []
                room_vars = {} # room_vars[r_id] = list of teaching vars in this room today
                
                for t_id in day_t_ids:
                    # Find all vars for this section in this slot
                    # Including specific section assignments and elective (None) assignments
                    v_list = []
                    for (a_id, h_type, r_id, t), v in self.x.items():
                        if t == t_id:
                            a = next(ast for ast in self.assignments if ast.id == a_id)
                            # If assignment belongs to this section directly
                            if a.section_id == s_id:
                                v_list.append(v)
                                room_vars.setdefault(r_id, []).append(v)
                            # Or if it's an elective group that applies to this section's department/semester
                            elif a.section_id is None:
                                c = self.courses.get(a.course_id)
                                sec = self.sections.get(s_id)
                                if c and sec and c.department_id == sec.department_id:
                                    # Very simplified checking for elective applicability 
                                    v_list.append(v)
                                    room_vars.setdefault(r_id, []).append(v)
                                
                    if v_list:
                        is_teaching = self.model.new_bool_var(f"s_{s_id}_{day}_{t_id}_teaching")
                        self.model.add_max_equality(is_teaching, v_list)
                        s_teaching_slots.append((t_id, is_teaching))
                
                if not s_teaching_slots:
                    continue
                    
                total_teaching = sum(var for _, var in s_teaching_slots)
                is_active_day = self.model.new_bool_var(f"s_{s_id}_{day}_active")
                self.model.add_max_equality(is_active_day, [var for _, var in s_teaching_slots])
                
                # Gap calculation
                first_slot_idx = self.model.new_int_var(0, len(day_t_ids), f"s_{s_id}_{day}_first")
                last_slot_idx = self.model.new_int_var(0, len(day_t_ids), f"s_{s_id}_{day}_last")
                
                for i, (t_id, var) in enumerate(s_teaching_slots):
                    self.model.add(first_slot_idx <= i).only_enforce_if(var)
                    self.model.add(last_slot_idx >= i).only_enforce_if(var)
                    
                self.model.add(first_slot_idx == 0).only_enforce_if(is_active_day.Not())
                self.model.add(last_slot_idx == 0).only_enforce_if(is_active_day.Not())
                
                gap_expr = last_slot_idx - first_slot_idx + is_active_day - total_teaching
                gap_var = self.model.new_int_var(0, len(day_t_ids), f"s_{s_id}_{day}_gap")
                self.model.add(gap_var == gap_expr)
                
                objective_terms.append(gap_var * W_STUDENT_GAP)
                
                # Room changes: count distinct rooms used today
                rooms_used = []
                for r_id, v_list in room_vars.items():
                    r_used = self.model.new_bool_var(f"s_{s_id}_{day}_r_{r_id}_used")
                    self.model.add_max_equality(r_used, v_list)
                    rooms_used.append(r_used)
                    
                total_rooms_used = sum(rooms_used)
                
                # Penalty is total_rooms_used - 1 (if active day)
                room_change_penalty = self.model.new_int_var(0, len(self.rooms), f"s_{s_id}_{day}_room_change")
                # When active, penalty = total_rooms_used - 1
                # When inactive, total_rooms_used is 0, we want penalty = 0.
                self.model.add(room_change_penalty == total_rooms_used - is_active_day)
                
                objective_terms.append(room_change_penalty * W_ROOM_CHANGE)

        # 7. Minimal Perturbation Objective: Penalize deviations from baseline schedule
        if self.previous_entries:
            prev_by_assignment = defaultdict(list)
            for pe in self.previous_entries:
                if isinstance(pe, tuple):
                    pa_id, ph_type, pr_id, pt_id = pe
                elif isinstance(pe, dict):
                    pa_id, ph_type, pr_id, pt_id = pe["course_assignment_id"], pe["hour_type"], pe["room_id"], pe["slot_id"]
                else:
                    pa_id, ph_type, pr_id, pt_id = pe.course_assignment_id, pe.hour_type, pe.room_id, pe.slot_id
                prev_by_assignment[(pa_id, ph_type)].append((pr_id, pt_id))

            for (a_id, h_type, r_id, t_id), v in self.x.items():
                prev_locs = prev_by_assignment.get((a_id, h_type), [])
                if prev_locs:
                    if (r_id, t_id) not in prev_locs:
                        slot_matched = any(pt == t_id for (pr, pt) in prev_locs)
                        room_matched = any(pr == r_id for (pr, pt) in prev_locs)
                        penalty = 0
                        if not slot_matched:
                            penalty += self.perturbation_penalty_slot
                        if not room_matched:
                            penalty += self.perturbation_penalty_room
                        if penalty > 0:
                            objective_terms.append(v * penalty)

        if objective_terms:
            self.model.minimize(sum(objective_terms))

    def _diagnose_infeasibility(self) -> list[str]:
        diagnostics = []
        # 1. room supply vs. required room-hours per department
        total_required_hours = 0
        for a in self.assignments:
            c = self.courses.get(a.course_id)
            if c:
                total_required_hours += c.lecture_hours + c.tutorial_hours + c.practical_hours
                
        total_room_slots = len(self.rooms) * len(self.slots)
        if total_required_hours > total_room_slots:
            diagnostics.append(f"Room capacity shortage: Need {total_required_hours} room-slots but only {total_room_slots} are available. Suggest adding {total_required_hours - total_room_slots} more slots or rooms.")
            
        # 2. faculty availability hours vs. required teaching hours
        for f in self.faculty.values():
            f_req = 0
            for a in self.assignments:
                if a.faculty_id == f.id:
                    c = self.courses.get(a.course_id)
                    if c:
                        f_req += c.lecture_hours + c.tutorial_hours + c.practical_hours
            
            f_avail = sum(1 for slot_id, av in self.faculty_availability.get(f.id, {}).items() if av.availability in ('AVAILABLE', 'PREFERRED') and slot_id in self.slots)
            if f_req > f_avail:
                diagnostics.append(f"Faculty availability shortage: Faculty ID {f.id} needs {f_req} teaching hours but only provided {f_avail} available slots. Suggest adding {f_req - f_avail} more available slots for this faculty.")

        # 3. lab room count vs. lab-course demand
        lab_courses = [c for c in self.courses.values() if c.requires_lab or c.course_type == 'LAB']
        total_lab_hours = 0
        for a in self.assignments:
            c = self.courses.get(a.course_id)
            if c and c in lab_courses:
                total_lab_hours += c.practical_hours if c.practical_hours > 0 else (c.lecture_hours + c.tutorial_hours)
                
        lab_rooms = [r for r in self.rooms.values() if r.room_type == 'LAB']
        total_lab_slots = len(lab_rooms) * len(self.slots)
        if total_lab_hours > total_lab_slots:
            diagnostics.append(f"Lab capacity shortage: Need {total_lab_hours} lab room-slots but only {total_lab_slots} are available. Suggest adding {total_lab_hours - total_lab_slots} more slots or lab rooms.")
            
        # 4. elective group overlap count vs. available parallel slots
        for eg in self.input.elective_groups:
            eg_courses = [egc.course_id for egc in self.input.elective_group_courses if egc.group_id == eg.id]
            if len(eg_courses) > len(self.slots):
                 diagnostics.append(f"Elective group bottleneck: Elective Group ID {eg.id} has {len(eg_courses)} courses but only {len(self.slots)} valid slots exist. Parallel courses will unavoidably collide.")
        
        if not diagnostics:
            diagnostics.append("No obvious aggregate shortages detected. The infeasibility is likely due to complex combinatorics (e.g. specific faculty + room + section constraints locking up).")
            
        return diagnostics

    def solve(self) -> SolverResult:
        start_time = time.time()
        
        success, msg = self.build_model()
        if not success:
            return SolverResult(
                feasible=False,
                status="INFEASIBLE_AT_BUILD",
                message=msg,
                solve_time_seconds=time.time() - start_time,
                diagnostics=self._diagnose_infeasibility()
            )
            
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit
        solver.parameters.num_search_workers = 8
        
        status = solver.solve(self.model)
        solve_time = time.time() - start_time
        
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            entries = []
            for (a_id, h_type, r_id, t_id), v in self.x.items():
                if solver.value(v) == 1:
                    entries.append(TimetableEntryResult(
                        course_assignment_id=a_id,
                        room_id=r_id,
                        slot_id=t_id,
                        hour_type=h_type
                    ))
            
            return SolverResult(
                feasible=True,
                status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
                message=f"Found {len(entries)} assignments.",
                entries=entries,
                solve_time_seconds=solve_time
            )
        elif status == cp_model.INFEASIBLE:
            return SolverResult(
                feasible=False,
                status="INFEASIBLE",
                message="No feasible timetable exists with the current constraints.",
                solve_time_seconds=solve_time,
                diagnostics=self._diagnose_infeasibility()
            )
        else:
            return SolverResult(
                feasible=False,
                status="UNKNOWN",
                message="Solver reached time limit without finding a solution.",
                solve_time_seconds=solve_time
            )
