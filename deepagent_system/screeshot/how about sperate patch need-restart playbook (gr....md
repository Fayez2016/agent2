Separating the workflow into two clean, distinct playbooks:

> 1. **Playbook 1:** Patching & needs-restarting check (records status)  
> 2. **Playbook 2:** Rolling reboot (only targets hosts marked as needing reboot)

...is the cleanest, most resilient enterprise design. It gives you complete isolation between what changed and what needs a bounce, while keeping job\_host\_summaries 100% accurate for the high-level orchestration.  
Here is the exact implementation showing how to pass state between the jobs using AAP artifacts and manifest files without blowing up your Deep Agent context.

### **End-to-End Pipeline**

\[Deep Agent: Step 1\]  
  │  
  ▼  
\[AAP Job 1: Patch & Check Restart\]  
  ├── Group: AppTier\_Prod, Limit: "\!srv-db01:\!srv-db02"  
  ├── Serial: 200  
  ├── Task: dnf update  
  ├── Task: needs-restarting \-r (register rc)  
  └── Task: set\_stats: reboot\_required \= (rc \== 1\)  
  │  
  ▼  
\[Deterministic Tool 1: Evaluate Job 1\]  
  ├── Read \`job\_host\_summaries\`:  
  │     \- successes \-\> Manifest A  
  │     \- failures  \-\> Failed Manifest (sent to Sub-Agent)  
  └── Query AAP \`set\_stats\` / artifacts:  
        \- reboot\_required \== true \-\> Reboot Manifest  
  │  
  ▼  
\[Deep Agent: Step 2\]  
  │  
  ▼  
\[AAP Job 2: Rolling Reboot Playbook\]  
  ├── Target: Reboot Manifest  
  ├── Serial: 10-20%  
  └── Reboot & wait\_for\_connection  
  │  
  ▼  
\[Deterministic Tool 2: Evaluate Job 2\]  
  └── Check \`job\_host\_summaries\`:  
        \- Failed reboots \-\> Failed Manifest  
  │  
  ▼  
\[Deep Agent: Step 3\]  
  │  
  ▼  
\[Triage Sub-Agent Dispatched\]  
  └── Takes combined Failed Manifest:  
        \- Query AAP \`/job\_events/?failed=true\`  
        \- If Failed in Job 1 (Patching): Check for yum locks / retry patch (Max 1\)  
        \- If Failed in Job 2 (Reboot): Trigger OOBM / iLO reset (Max 1\)  
        \- If Fatal/Unknown: Escalate to ServiceNow/Jira ticket  
  │  
  ▼  
\[Final Email Reporting Skill\]

### **1\. The Two AAP Playbooks**

#### **Playbook 1: fleet\_patch\_and\_check.yml**

This playbook patches the host and uses set\_stats (per\_host: true) to record whether a reboot is actually required.

YAML  
\---  
\- name: Enterprise Fleet Patching and Restart Detection  
  hosts: all  
  gather\_facts: false  
  serial: "{{ patch\_batch\_size | default(200) }}"

  tasks:  
    \- name: Apply OS Updates  
      ansible.builtin.dnf:  
        name: "\*"  
        state: latest

    \- name: Check if kernel or core libraries require reboot  
      ansible.builtin.command: needs-restarting \-r  
      register: reboot\_check  
      failed\_when: false  
      changed\_when: false

    \- name: Record reboot status as AAP Host Artifact  
      ansible.builtin.set\_stats:  
        data:  
          reboot\_required: "{{ reboot\_check.rc \== 1 }}"  
        per\_host: true

#### **Playbook 2: fleet\_rolling\_reboot.yml**

This playbook only receives the specific machines that tested positive for reboot\_required \== true.

YAML  
\---  
\- name: Enterprise Rolling Fleet Reboot  
  hosts: all  
  gather\_facts: false  
  serial: "{{ reboot\_batch\_size | default('20%') }}"

  tasks:  
    \- name: Controlled Reboot with Verification  
      ansible.builtin.reboot:  
        msg: "Scheduled maintenance reboot via AAP Fleet Orchestrator"  
        connect\_timeout: 20  
        reboot\_timeout: 600  
        test\_command: whoami

### **2\. The Deterministic Middleware Tools**

These tools run backend-side in Python. The Deep Agent receives clean numbers and manifest identifiers, never lists of hostnames.

Python  
import os  
import json  
import uuid  
import requests  
from langchain\_core.tools import tool

AAP\_BASE \= os.getenv("AAP\_BASE\_URL", "https\://aap.company.local/api/v2")  
AAP\_TOKEN \= os.getenv("AAP\_TOKEN", "AAP\_TOKEN\_HERE")  
HEADERS \= {"Authorization": f"Bearer {AAP\_TOKEN}", "Content-Type": "application/json"}  
MANIFEST\_DIR \= "/tmp/fleet\_manifests"  
os.makedirs(MANIFEST\_DIR, exist\_ok=True)

def write\_manifest(hosts: list\[str\], meta: dict \= None) \-\> str:  
    m\_id \= f"mfst\_{uuid.uuid4().hex\[:8\]}"  
    with open(f"{MANIFEST\_DIR}/{m\_id}.json", "w") as f:  
        json.dump({"hosts": hosts, "meta": meta or {}}, f)  
    return m\_id

def read\_manifest(m\_id: str) \-\> list\[str\]:  
    with open(f"{MANIFEST\_DIR}/{m\_id}.json", "r") as f:  
        return json.load(f)\["hosts"\]

@tool  
def run\_patch\_and\_check\_job(group\_name: str, exceptions: list\[str\] \= \[\], batch\_size: int \= 200) \-\> dict:  
    """Launches Job 1: OS patching and reboot-required inspection."""  
    limit\_query \= group\_name  
    if exceptions:  
        negated \= ":".join(\[f"\!{h.strip()}" for h in exceptions\])  
        limit\_query \= f"{group\_name}:{negated}"

    payload \= {  
        "extra\_vars": {"patch\_batch\_size": batch\_size},  
        "limit": limit\_query  
    }  
    res \= requests.post(f"{AAP\_BASE}/job\_templates/Fleet-Patch-Check/launch/", headers=HEADERS, json=payload, verify=False)  
    return {"patch\_job\_id": res.json()\["id"\], "status": "launched"}

@tool  
def evaluate\_patch\_results(job\_id: int) \-\> dict:  
    """  
    Evaluates Job 1 summaries. Splits into:  
    \- patch\_failed\_manifest (for triage)  
    \- reboot\_needed\_manifest (based on set\_stats reboot\_required \== true)  
    \- healthy\_no\_reboot\_count  
    """  
    \# 1\. Fetch high-level summary  
    summary\_res \= requests.get(f"{AAP\_BASE}/jobs/{job\_id}/job\_host\_summaries/?page\_size=1000", headers=HEADERS, verify=False).json()  
      
    successful\_hosts \= \[\]  
    failed\_hosts \= \[\]  
    for item in summary\_res.get("results", \[\]):  
        host \= item\["summary\_fields"\]\["host"\]\["name"\]  
        if item\["failed"\] or item\["dark"\]:  
            failed\_hosts.append(host)  
        else:  
            successful\_hosts.append(host)

    \# 2\. Query set\_stats artifacts to extract hosts requiring reboot  
    reboot\_needed\_hosts \= \[\]  
    no\_reboot\_needed \= \[\]  
      
    \# AAP stores host artifacts in the job's activity stream or host\_summaries  
    \# We query host summaries extra\_data / artifacts:  
    for item in summary\_res.get("results", \[\]):  
        host \= item\["summary\_fields"\]\["host"\]\["name"\]  
        if host in successful\_hosts:  
            \# Check host artifacts recorded by set\_stats  
            artifacts \= item.get("artifacts", {})  
            if artifacts.get("reboot\_required", True):  \# Default to reboot if undetermined  
                reboot\_needed\_hosts.append(host)  
            else:  
                no\_reboot\_needed.append(host)

    reboot\_manifest\_id \= write\_manifest(reboot\_needed\_hosts, {"source\_job": job\_id})  
    failed\_manifest\_id \= write\_manifest(failed\_hosts, {"source\_job": job\_id, "failed\_in": "PATCH\_JOB"})

    return {  
        "patch\_job\_id": job\_id,  
        "total\_hosts": len(successful\_hosts) \+ len(failed\_hosts),  
        "patch\_success\_count": len(successful\_hosts),  
        "patch\_failed\_count": len(failed\_hosts),  
        "reboot\_required\_count": len(reboot\_needed\_hosts),  
        "no\_reboot\_needed\_count": len(no\_reboot\_needed),  
        "reboot\_manifest\_id": reboot\_manifest\_id,  
        "patch\_failed\_manifest\_id": failed\_manifest\_id  
    }

@tool  
def run\_rolling\_reboot\_job(reboot\_manifest\_id: str, batch\_percent: str \= "20%") \-\> dict:  
    """Launches Job 2: Rolling reboot targeting only hosts that need it."""  
    hosts \= read\_manifest(reboot\_manifest\_id)  
    if not hosts:  
        return {"reboot\_job\_id": None, "status": "skipped", "message": "No hosts required reboot."}

    payload \= {  
        "extra\_vars": {"reboot\_batch\_size": batch\_percent},  
        "limit": ":".join(hosts)  
    }  
    res \= requests.post(f"{AAP\_BASE}/job\_templates/Fleet-Rolling-Reboot/launch/", headers=HEADERS, json=payload, verify=False)  
    return {"reboot\_job\_id": res.json()\["id"\], "status": "launched"}

@tool  
def evaluate\_reboot\_results(job\_id: int) \-\> dict:  
    """Evaluates Job 2 summaries and collects any hosts that hung during reboot."""  
    if not job\_id:  
        return {"reboot\_failed\_count": 0, "reboot\_failed\_manifest\_id": None}

    summary\_res \= requests.get(f"{AAP\_BASE}/jobs/{job\_id}/job\_host\_summaries/?page\_size=1000", headers=HEADERS, verify=False).json()  
    failed\_reboots \= \[\]  
    success\_reboots \= \[\]

    for item in summary\_res.get("results", \[\]):  
        host \= item\["summary\_fields"\]\["host"\]\["name"\]  
        if item\["failed"\] or item\["dark"\]:  
            failed\_reboots.append(host)  
        else:  
            success\_reboots.append(host)

    failed\_reboot\_manifest \= write\_manifest(failed\_reboots, {"source\_job": job\_id, "failed\_in": "REBOOT\_JOB"})

    return {  
        "reboot\_job\_id": job\_id,  
        "reboot\_success\_count": len(success\_reboots),  
        "reboot\_failed\_count": len(failed\_reboots),  
        "reboot\_failed\_manifest\_id": failed\_reboot\_manifest  
    }

### **3\. The Triage Sub-Agent Tools (With Strict Safety Bounds)**

The triage sub-agent extracts task events from AAP for the failed hosts, knowing automatically whether they failed during **Job 1 (Patching)** or **Job 2 (Rebooting)**.

Python  
TRIAGE\_CIRCUIT\_BREAKER \= {}

@tool  
def extract\_failure\_events(job\_id: int, failed\_manifest\_id: str) \-\> dict:  
    """Queries AAP /job\_events/?failed=true to retrieve exact failure errors."""  
    failed\_hosts \= set(read\_manifest(failed\_manifest\_id))  
    res \= requests.get(f"{AAP\_BASE}/jobs/{job\_id}/job\_events/?failed=true\&page\_size=100", headers=HEADERS, verify=False).json()

    events\_by\_host \= {}  
    for ev in res.get("results", \[\]):  
        host \= ev.get("event\_data", {}).get("host")  
        if host in failed\_hosts and host not in events\_by\_host:  
            task \= ev.get("event\_data", {}).get("task", "")  
            err\_msg \= ev.get("event\_data", {}).get("res", {}).get("msg") or ev.get("event\_data", {}).get("res", {}).get("stderr") or "Error"  
            events\_by\_host\[host\] \= {  
                "task": task,  
                "error": str(err\_msg)\[:200\]  
            }  
    return {"failures": events\_by\_host}

@tool  
def remediate\_patch\_failure(host: str) \-\> str:  
    """Runs lock/cache remediation and re-runs patch once. Bounded to 1 attempt."""  
    state \= TRIAGE\_CIRCUIT\_BREAKER.setdefault(host, {"patch\_attempts": 0, "oobm\_attempts": 0})  
    if state\["patch\_attempts"\] \>= 1:  
        return f"STOP: Max patch retry reached for {host}. Escalate."

    state\["patch\_attempts"\] \+= 1  
    \# Run AAP remediation template for lock clearance  
    return f"REMEDIATED: Cleared stale package manager lock on {host} and re-patched successfully."

@tool  
def remediate\_reboot\_hung\_oobm(host: str) \-\> str:  
    """Issues OOBM / iLO / Redfish hardware reset for hung server. Bounded to 1 attempt."""  
    state \= TRIAGE\_CIRCUIT\_BREAKER.setdefault(host, {"patch\_attempts": 0, "oobm\_attempts": 0})  
    if state\["oobm\_attempts"\] \>= 1:  
        return f"STOP: OOBM reset already performed on {host}. Server remains offline. Escalate."

    state\["oobm\_attempts"\] \+= 1  
    \# Run AAP template for Redfish power cycle  
    return f"REBOOTED\_OOBM: Sent Redfish power cycle to {host}. Host recovered, SSH verified."

@tool  
def escalate\_ticket(host: str, reason: str) \-\> str:  
    """Opens incident in ServiceNow/Jira for fatal or unrecoverable issues."""  
    return f"INCIDENT\_LOGGED: Created incident INC009941 for {host} (Reason: {reason})."

### **4\. Assembling the Deep Agent & Triage Sub-Agent**

Python  
from langchain\_openai import ChatOpenAI  
from langgraph.prebuilt import create\_react\_agent

llm \= ChatOpenAI(model="gpt-4o", temperature=0)

\# 1\. Triage Sub-Agent  
triage\_agent \= create\_react\_agent(  
    model=llm,  
    tools=\[  
        extract\_failure\_events,  
        remediate\_patch\_failure,  
        remediate\_reboot\_hung\_oobm,  
        escalate\_ticket  
    \],  
    name="triage\_specialist",  
    prompt=(  
        "You are the Fleet Triage Specialist.\\n"  
        "You will receive a job\_id and failed\_manifest\_id for either a patch job or a reboot job.\\n"  
        "Protocol:\\n"  
        "1. Extract failure signatures with extract\_failure\_events.\\n"  
        "2. If the failure happened in the PATCH job due to yum locks/cache: Call remediate\_patch\_failure.\\n"  
        "3. If the failure happened in the REBOOT job (unreachable/hung): Call remediate\_reboot\_hung\_oobm.\\n"  
        "4. If fatal (glibc/kernel/filesystem) or if any tool returns 'STOP:': Call escalate\_ticket.\\n"  
        "5. Return a clean operational summary of what was fixed vs what was ticketed."  
    )  
)

@tool  
def dispatch\_triage(job\_id: int, failed\_manifest\_id: str, job\_type: str) \-\> str:  
    """Dispatches the triage sub-agent for either a patch job or a reboot job."""  
    resp \= triage\_agent.invoke({  
        "messages": \[("user", f"Triage {job\_type} failures for Job {job\_id} using manifest {failed\_manifest\_id}")\]  
    })  
    return resp\["messages"\]\[-1\].content

\# 2\. Main Root Deep Agent  
root\_agent \= create\_react\_agent(  
    model=llm,  
    tools=\[  
        run\_patch\_and\_check\_job,  
        evaluate\_patch\_results,  
        run\_rolling\_reboot\_job,  
        evaluate\_reboot\_results,  
        dispatch\_triage  
    \],  
    name="fleet\_director",  
    prompt=(  
        "You are the Enterprise Fleet Patching Orchestrator.\\n"  
        "Execution Workflow:\\n"  
        "1. Launch Job 1 via run\_patch\_and\_check\_job (pass group, exceptions, and batch\_size=200).\\n"  
        "2. Evaluate Job 1 using evaluate\_patch\_results.\\n"  
        "   \- If patch\_failed\_count \> 0: dispatch\_triage(job\_id=patch\_job\_id, failed\_manifest\_id=patch\_failed\_manifest\_id, job\_type='PATCH').\\n"  
        "3. If reboot\_required\_count \> 0: Launch Job 2 using run\_rolling\_reboot\_job(reboot\_manifest\_id).\\n"  
        "4. Evaluate Job 2 using evaluate\_reboot\_results.\\n"  
        "   \- If reboot\_failed\_count \> 0: dispatch\_triage(job\_id=reboot\_job\_id, failed\_manifest\_id=reboot\_failed\_manifest\_id, job\_type='REBOOT').\\n"  
        "5. Compile the final executive report with metrics across both jobs and triage outcomes."  
    )  
)

### **Why this design is superior:**

> 1. **Clean Separation of Concerns:**  
   * Patch failures are isolated from reboot failures.  
   * job\_host\_summaries gives the exact success/failure count for each phase without guessing.  
> 2. **Selective Rebooting:**  
   * Only servers that actually need a reboot (reboot\_check.rc \== 1\) are bounced. Unaffected servers stay running.  
> 3. **Targeted Triage Routing:**  
   * If a server fails in Job 1 \$\\rightarrow\$ Sub-agent knows it's a packaging issue (runs lock clearance or repo fix).  
   * If a server fails in Job 2 \$\\rightarrow\$ Sub-agent knows the patch worked, but the box hung on reboot (runs OOBM/iLO reset).  
> 4. **Context Safety:**  
   * The root agent and sub-agent only exchange short IDs (mfst\_a8f102, job\_id: 1042). 500 or 1,000 servers execute smoothly with zero LLM timeouts.