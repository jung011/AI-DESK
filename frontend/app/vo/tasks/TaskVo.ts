/**
 * task DTO — backend app.tasks.schemas 와 1:1.
 */
export interface TaskAttachmentItem {
  attachmentId: string;
  originalFilename: string;
  contentType: string;
  sizeBytes: number;
}

export type TaskStatus = 'todo' | 'in_progress' | 'done' | 'stuck' | 'canceled';

export interface TaskItem {
  taskId: string;
  agentId: string;
  agentName: string | null;
  content: string;
  status: TaskStatus;
  result: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  attachments: TaskAttachmentItem[];
}

export interface TaskListRs {
  items: TaskItem[];
}

export interface TaskCreateRq {
  agentId: string;
  content: string;
  attachmentIds: string[];
}
