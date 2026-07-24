import {
  mkdirSync,
  mkdtempSync,
  rmSync,
  writeFileSync,
} from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';
import { DatabaseSync } from 'node:sqlite';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  getWorkOrderById,
  getWorkOrderExportInfo,
  getWorkOrderSummary,
  listWorkOrders,
  parseWorkOrderQuery,
} from '../../packages/server/src/services/hermes/work-orders';

describe('work order service', () => {
  let directory: string;
  const originalReinsHome = process.env.REINS_HOME;
  const originalExportDirectory = process.env.REINS_WECOM_EXPORT_DIR;

  beforeEach(() => {
    directory = mkdtempSync(join(tmpdir(), 'reins-work-orders-'));
    process.env.REINS_HOME = directory;
    process.env.REINS_WECOM_EXPORT_DIR = join(directory, 'staff');

    const wecomDirectory = join(directory, 'wecom');
    mkdirSync(wecomDirectory, { recursive: true });
    const db = new DatabaseSync(join(wecomDirectory, 'wecom.sqlite'));
    db.exec(`
      CREATE TABLE wecom_records (
        id INTEGER PRIMARY KEY,
        created_at TEXT NOT NULL,
        kind TEXT NOT NULL,
        status TEXT NOT NULL,
        message TEXT NOT NULL,
        reply TEXT NOT NULL DEFAULT '',
        metadata_json TEXT NOT NULL DEFAULT '{}'
      )
    `);

    const insert = db.prepare(`
      INSERT INTO wecom_records (
        id, created_at, kind, status, message, reply, metadata_json
      ) VALUES (?, ?, 'work_order', ?, ?, ?, ?)
    `);
    insert.run(
      1,
      '2026-07-22T07:34:21+00:00',
      'open',
      '6栋楼道有垃圾',
      '',
      JSON.stringify({
        external_id: 't_cleaning_1',
        ticket_created_at: '2026-07-22 15:34:21',
        priority: 'high',
        category: '公共区域清扫',
        assigned_role: 'cleaning',
        assigned_role_label: '保洁',
        notification_recipients: ['cleaner-1'],
        location: '6栋2单元',
        description: '6栋楼道有垃圾需要清理',
        customer_assessment: '请保洁尽快处理',
        handling_requirements: '完成后在群里回复',
        resident_contact: '13600000000',
        notification_status: 'failed',
        notification_error: 'temporary error',
        api_updated_at: '2026-07-22 15:35:00',
      }),
    );
    insert.run(
      2,
      '2026-07-22T08:00:00+00:00',
      'resolved',
      '3栋404恢复供电',
      '已恢复',
      JSON.stringify({
        external_id: 't_repair_1',
        priority: 'normal',
        category: '公共设施维修',
        assigned_role: 'property',
        assigned_role_label: '物业维修',
        notification_recipients: ['property-1'],
        location: '3栋404',
        title: '停电',
        notification_status: 'sent',
        last_staff_responder: 'property-1',
        last_staff_reply_at: '2026-07-22 16:20:00',
      }),
    );
    db.close();
  });

  afterEach(() => {
    if (originalReinsHome === undefined) {
      delete process.env.REINS_HOME;
    } else {
      process.env.REINS_HOME = originalReinsHome;
    }
    if (originalExportDirectory === undefined) {
      delete process.env.REINS_WECOM_EXPORT_DIR;
    } else {
      process.env.REINS_WECOM_EXPORT_DIR = originalExportDirectory;
    }
    rmSync(directory, { recursive: true, force: true });
  });

  it('summarizes the ledger and exposes filter options', () => {
    const summary = getWorkOrderSummary();

    expect(summary.database_exists).toBe(true);
    expect(summary.total).toBe(2);
    expect(summary.pending).toBe(1);
    expect(summary.urgent).toBe(1);
    expect(summary.notification_failed).toBe(1);
    expect(summary.completed).toBe(1);
    expect(summary.filters.roles).toContainEqual({
      value: 'cleaning',
      label: '保洁',
    });
  });

  it('filters, searches, paginates, and returns details', () => {
    const result = listWorkOrders(
      parseWorkOrderQuery({
        role: 'cleaning',
        search: '楼道',
        limit: '10',
      }),
    );

    expect(result.total).toBe(1);
    expect(result.records[0]?.external_id).toBe('t_cleaning_1');
    expect(result.records[0]?.assignees).toEqual(['cleaner-1']);
    expect(getWorkOrderById(2).result).toBe('已恢复');
    expect(() => getWorkOrderById('invalid')).toThrow('Invalid');
  });

  it('does not expose resident identifiers from raw fallback messages', () => {
    const db = new DatabaseSync(join(directory, 'wecom', 'wecom.sqlite'));
    db.prepare(`
      INSERT INTO wecom_records (
        id, created_at, kind, status, message, reply, metadata_json
      ) VALUES (?, ?, 'work_order', 'open', ?, '', '{}')
    `).run(
      3,
      '2026-07-22T09:00:00+00:00',
      '居民反映电梯故障\n居民标识：private-reference\n请尽快处理',
    );
    db.close();

    const record = getWorkOrderById(3);

    expect(record.issue).toContain('居民反映电梯故障');
    expect(record.issue).not.toContain('private-reference');
    expect(record).not.toHaveProperty('message');
  });

  it('reports the fixed workbook and optional visible mirror paths', () => {
    const workbook = join(directory, 'wecom', 'records.xlsx');
    writeFileSync(workbook, 'workbook');
    delete process.env.REINS_WECOM_EXPORT_DIR;
    writeFileSync(
      join(directory, '.env'),
      `REINS_WECOM_EXPORT_DIR="${join(directory, 'staff')}"\n`,
    );

    const info = getWorkOrderExportInfo();

    expect(info.available).toBe(true);
    expect(info.file_name).toBe('社区工单台账.xlsx');
    expect(info.visible_path).toBe(
      join(directory, 'staff', '社区工单台账.xlsx'),
    );
    expect(info.updated_at).not.toBe('');
  });
});
