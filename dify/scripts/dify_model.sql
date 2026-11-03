-- 查看 Dify 中注册的自定义模型。
\pset pager off
SELECT provider_name, model_name, model_type, is_valid
FROM provider_models
ORDER BY provider_name, model_name;
