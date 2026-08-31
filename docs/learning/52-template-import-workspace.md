# 模块 52：模板导入草稿工作区

管理端现在可以通过 `POST /api/v1/admin/tutorial-drafts/from-template/{template_id}` 导入模板。接口只创建编辑工作区，返回的 `promoted_graph_id` 仍为 `null`；管理员必须在真实设备录制、替换锚点、校验并提升/发布。
