-- 查看 Dify 最近一轮 Chatflow 的节点执行记录。
-- 把 :'app_id' 换成实际 app_id，或直接编辑下面的 WHERE 条件。
\pset pager off
\pset format aligned
SELECT node_id,
       node_type,
       title,
       status,
       round(elapsed_time::numeric, 3) AS seconds,
       left(coalesce(outputs, ''), 220) AS outputs
FROM workflow_node_executions
WHERE app_id = :'app_id'
ORDER BY created_at DESC
LIMIT 20;
