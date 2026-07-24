import { createReadStream } from 'fs';
import Router from '@koa/router';
import {
  getWorkOrderById,
  getWorkOrderExportInfo,
  getWorkOrderSummary,
  getWorkOrderWorkbookPath,
  listWorkOrders,
  parseWorkOrderQuery,
} from '../../services/hermes/work-orders';

export const workOrderRoutes = new Router();

function handleError(ctx: any, err: any) {
  const message = err?.message || 'Work order request failed';
  if (/not found/i.test(message)) {
    ctx.status = 404;
  } else if (/invalid|required|limit|offset/i.test(message)) {
    ctx.status = 400;
  } else {
    ctx.status = 500;
  }
  ctx.body = { error: message };
}

workOrderRoutes.get('/api/hermes/work-orders/summary', async (ctx) => {
  try {
    ctx.body = getWorkOrderSummary();
  } catch (err: any) {
    handleError(ctx, err);
  }
});

workOrderRoutes.get('/api/hermes/work-orders/export', async (ctx) => {
  try {
    const info = getWorkOrderExportInfo();
    if (!info.available) {
      ctx.status = 404;
      ctx.body = { error: 'Work order workbook not found.' };
      return;
    }

    const encoded = encodeURIComponent(info.file_name);
    ctx.set(
      'Content-Type',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    );
    ctx.set(
      'Content-Disposition',
      `attachment; filename="community-work-orders.xlsx"; filename*=UTF-8''${encoded}`,
    );
    ctx.set('Cache-Control', 'no-store');
    ctx.body = createReadStream(getWorkOrderWorkbookPath());
  } catch (err: any) {
    handleError(ctx, err);
  }
});

workOrderRoutes.get('/api/hermes/work-orders', async (ctx) => {
  try {
    const query = parseWorkOrderQuery(ctx.query as Record<string, unknown>);
    ctx.body = listWorkOrders(query);
  } catch (err: any) {
    handleError(ctx, err);
  }
});

workOrderRoutes.get('/api/hermes/work-orders/:id', async (ctx) => {
  try {
    ctx.body = { record: getWorkOrderById(ctx.params.id) };
  } catch (err: any) {
    handleError(ctx, err);
  }
});
