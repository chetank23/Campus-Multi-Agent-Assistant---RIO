import time
from typing import List, Dict, Tuple
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

class TimetableSolver:
    def __init__(self, opt_input: OptimizerInput, time_limit: int = 60):
        self.input = opt_input
        self.time_limit = time_limit
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
        # Filter slots by faculty availability
        eligible = []
        for t_id, slot in self.slots.items():
            # If no availability record is found, we might assume available, 
            # but to be strict, if faculty have availability records, we respect them.
            # "Faculty can only be scheduled in permitted time slots."
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
        r_t_vars = defaultdict(list)
        
        self.assignment_vars = []
        
        for a in self.assignments:
            course = self.courses[a.course_id]
            f_id = a.faculty_id
            sec_id = a.section_id
            
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
                    return False, f"No eligible rooms for {h_type} of course {course.course_code}"
                if len(eligible_slots) < req_hours:
                    return False, f"Not enough available slots for faculty {f_id} teaching {course.course_code}"
                
                var_list = []
                for r_id in eligible_rooms:
                    for t_id in eligible_slots:
                        var_name = f"x_a{a.id}_{h_type}_r{r_id}_t{t_id}"
                        v = self.model.NewBoolVar(var_name)
                        self.x[(a.id, h_type, r_id, t_id)] = v
                        var_list.append(v)
                        
                        a_r_t_vars[(a.id, h_type)].append(v)
                        f_t_vars[(f_id, t_id)].append(v)
                        if sec_id:
                            s_t_vars[(sec_id, t_id)].append(v)
                        r_t_vars[(r_id, t_id)].append(v)
                
                self.assignment_vars.append((a, h_type, req_hours, var_list))
                
        # 2. Hard Constraints
        
        # A. Required Course Hours
        for a, h_type, req_hours, var_list in self.assignment_vars:
            self.model.AddExactlyOne(var_list) if req_hours == 1 else self.model.Add(sum(var_list) == req_hours)
            
        # B. Faculty Conflict (<= 1 per slot)
        for (f_id, t_id), vars_in_slot in f_t_vars.items():
            if len(vars_in_slot) > 1:
                self.model.AddAtMostOne(vars_in_slot)
                
        # C. Section Conflict (<= 1 per slot)
        for (sec_id, t_id), vars_in_slot in s_t_vars.items():
            if len(vars_in_slot) > 1:
                self.model.AddAtMostOne(vars_in_slot)
                
        # D. Room Conflict (<= 1 per slot)
        for (r_id, t_id), vars_in_slot in r_t_vars.items():
            if len(vars_in_slot) > 1:
                self.model.AddAtMostOne(vars_in_slot)
                
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
                    self.model.AddAtMostOne(vars_in_slot)
                
        # 3. Objective (Soft Constraint)
        # Maximize faculty preferences
        objective_terms = []
        for (a_id, h_type, r_id, t_id), v in self.x.items():
            a = next(ast for ast in self.assignments if ast.id == a_id)
            pref = 0
            fa = self.faculty_availability[a.faculty_id].get(t_id)
            if fa and fa.availability == 'PREFERRED':
                pref = fa.preference if fa.preference > 0 else 1
            if pref > 0:
                objective_terms.append(v * pref)
                
        if objective_terms:
            self.model.Maximize(sum(objective_terms))
            
        return True, "Model built successfully"

    def solve(self) -> SolverResult:
        start_time = time.time()
        
        success, msg = self.build_model()
        if not success:
            return SolverResult(
                feasible=False,
                status="INFEASIBLE_AT_BUILD",
                message=msg,
                solve_time_seconds=time.time() - start_time
            )
            
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit
        solver.parameters.num_search_workers = 8
        
        status = solver.Solve(self.model)
        solve_time = time.time() - start_time
        
        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            entries = []
            for (a_id, h_type, r_id, t_id), v in self.x.items():
                if solver.Value(v) == 1:
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
                solve_time_seconds=solve_time
            )
        else:
            return SolverResult(
                feasible=False,
                status="UNKNOWN",
                message="Solver reached time limit without finding a solution.",
                solve_time_seconds=solve_time
            )
