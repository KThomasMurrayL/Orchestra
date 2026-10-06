import { tool } from "@opencode-ai/plugin"
import fs from "node:fs"
import path from "node:path"

const ORCH_AGENT = process.env.ORCHESTRA_AGENT ?? "orchestra"
const TERMINAL = new Set(["done", "failed", "cancelled"])

function inbox(): string {
  const dir = process.env.ORCHESTRA_INBOX
  if (!dir) throw new Error("ORCHESTRA_INBOX is not set; worker dispatch is unavailable")
  fs.mkdirSync(dir, { recursive: true })
  return dir
}

function statusPath(id: string): string {
  return path.join(inbox(), `${id}.status.json`)
}

function taskPath(id: string): string {
  return path.join(inbox(), `${id}.task.json`)
}

function readStatus(id: string): Record<string, any> | null {
  try {
    return JSON.parse(fs.readFileSync(statusPath(id), "utf8"))
  } catch {
    return null
  }
}

function readTask(id: string): Record<string, any> | null {
  try {
    return JSON.parse(fs.readFileSync(taskPath(id), "utf8"))
  } catch {
    return null
  }
}

function taskIds(): string[] {
  return fs
    .readdirSync(inbox())
    .filter((name) => name.endsWith(".task.json"))
    .map((name) => name.slice(0, -".task.json".length))
    .sort()
}

function taskOwner(id: string): string | null {
  const task = readTask(id)
  return task && typeof task.orchestrator === "string" ? task.orchestrator : null
}

function ownedTaskIds(sessionID: string): string[] {
  return taskIds().filter((id) => taskOwner(id) === sessionID)
}

function summarize(status: Record<string, any>, task?: Record<string, any> | null): string {
  const lines = [`[${status.status ?? "unknown"}] ${status.id} (${status.agent ?? "?"}) "${status.title ?? ""}"`]
  if (status.detail) lines.push(`  activity: ${String(status.detail).slice(0, 240)}`)
  if (status.sessionID) lines.push(`  session: ${status.sessionID}`)
  if (status.resultPreview) lines.push(`  result: ${String(status.resultPreview).replace(/\s+/g, " ").slice(0, 700)}`)
  if (status.error) lines.push(`  error: ${String(status.error).replace(/\s+/g, " ").slice(0, 400)}`)
  if (task?.prompt && !status.started) lines.push(`  prompt: ${String(task.prompt).replace(/\s+/g, " ").slice(0, 300)}`)
  return lines.join("\n")
}

function statusFor(id: string): Record<string, any> {
  const status = readStatus(id)
  if (status) return status
  const task = readTask(id)
  return { id, title: task?.title ?? id, agent: task?.agent ?? "?", status: "queued", detail: "not picked up yet" }
}

function denyNonOrchestrator(agent: string): string | null {
  if (agent !== ORCH_AGENT) {
    return `This tool is reserved for the "${ORCH_AGENT}" agent. You are "${agent}": do your assigned task and report back instead.`
  }
  return null
}

function denyForeignTask(id: string, sessionID: string): string | null {
  const owner = taskOwner(id)
  if (owner === sessionID) return null
  if (owner === null) return `Task ${id} does not exist in this run.`
  return `Task ${id} was dispatched by another orchestrator; you can only manage your own tasks.`
}

export const OrchestraPlugin = async () => ({
  tool: {
    dispatch_task: tool({
      description:
        "Dispatch a new worker agent instance to execute one well-scoped task. The worker runs as its own process with its own session and has no memory of this conversation, so the prompt must be fully self-contained.",
      args: {
        title: tool.schema.string().describe("Short human-readable title for the task"),
        agent: tool.schema.enum(["builder", "researcher", "tester", "reviewer"]).describe("Worker role to run"),
        prompt: tool.schema
          .string()
          .describe("Complete, self-contained instructions including context, deliverable, file paths, and acceptance criteria"),
      },
      async execute(args, context) {
        const denied = denyNonOrchestrator(context.agent)
        if (denied) return { title: "denied", output: denied }
        const id = `t-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
        const task = {
          id,
          title: args.title,
          agent: args.agent,
          prompt: args.prompt,
          orchestrator: context.sessionID,
          created: Date.now(),
        }
        fs.writeFileSync(taskPath(id), JSON.stringify(task, null, 2))
        return {
          title: `Dispatched ${id} to ${args.agent}`,
          output: `Dispatched ${id} ("${args.title}") to ${args.agent}. Use check_tasks or wait_tasks to monitor progress.`,
        }
      },
    }),
    check_tasks: tool({
      description:
        "Show the current status of tasks you dispatched: queued, running activity, completion results, or errors. Without an id, lists every task you dispatched in this run.",
      args: {
        id: tool.schema.string().optional().describe("Specific task id to check; omit to list your tasks"),
      },
      async execute(args, context) {
        const denied = denyNonOrchestrator(context.agent)
        if (denied) return { title: "denied", output: denied }
        if (args.id) {
          const foreign = denyForeignTask(args.id, context.sessionID)
          if (foreign) return { title: "not yours", output: foreign }
          return { title: `status ${statusFor(args.id).status}`, output: summarize(statusFor(args.id), readTask(args.id)) }
        }
        const ids = ownedTaskIds(context.sessionID)
        if (ids.length === 0) return { title: "no tasks", output: "You have not dispatched any tasks in this run." }
        return {
          title: `${ids.length} task(s)`,
          output: ids.map((id) => summarize(statusFor(id), readTask(id))).join("\n\n"),
        }
      },
    }),
    wait_tasks: tool({
      description:
        "Block until the given tasks (or all tasks you dispatched) reach a terminal state (done, failed, cancelled), then report their results. Use this to orchestrate multi-step work.",
      args: {
        ids: tool.schema.array(tool.schema.string()).optional().describe("Task ids to wait for; omit to wait for all your tasks"),
        timeout_seconds: tool.schema.number().optional().describe("Maximum time to wait, default 120, capped at 300"),
      },
      async execute(args, context) {
        const denied = denyNonOrchestrator(context.agent)
        if (denied) return { title: "denied", output: denied }
        const requested = args.ids && args.ids.length > 0 ? args.ids : ownedTaskIds(context.sessionID)
        const ids = requested.filter((id) => taskOwner(id) === context.sessionID)
        if (ids.length === 0) return { title: "no tasks", output: "You have not dispatched any tasks in this run." }
        const timeout = Math.min(Math.max(args.timeout_seconds ?? 120, 5), 300) * 1000
        const deadline = Date.now() + timeout
        let statuses: Array<Record<string, any>> = []
        while (true) {
          statuses = ids.map(statusFor)
          if (statuses.every((status) => TERMINAL.has(String(status.status)))) break
          if (Date.now() >= deadline) {
            return {
              title: "timed out",
              output: `Timed out after ${timeout / 1000}s.\n\n` + statuses.map((status) => summarize(status)).join("\n\n"),
            }
          }
          await new Promise((resolve) => setTimeout(resolve, 2000))
        }
        return { title: "tasks finished", output: statuses.map((status) => summarize(status)).join("\n\n") }
      },
    }),
    cancel_task: tool({
      description: "Cancel one of your queued or running tasks. The worker process is terminated.",
      args: {
        id: tool.schema.string().describe("Task id to cancel"),
      },
      async execute(args, context) {
        const denied = denyNonOrchestrator(context.agent)
        if (denied) return { title: "denied", output: denied }
        const foreign = denyForeignTask(args.id, context.sessionID)
        if (foreign) return { title: "not yours", output: foreign }
        const status = readStatus(args.id)
        if (status && TERMINAL.has(String(status.status))) {
          return { title: "already finished", output: `Task ${args.id} is already ${status.status}.` }
        }
        fs.writeFileSync(path.join(inbox(), `${args.id}.cancel`), String(Date.now()))
        return { title: `cancelling ${args.id}`, output: `Cancellation requested for ${args.id}.` }
      },
    }),
  },
})

export default OrchestraPlugin
