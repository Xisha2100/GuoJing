# 模块 56：管理网页求助面板

React 管理台新增求助摘要面板和“处理下一批”按钮。它只调用受保护的 reviews/process-next API，不展示截图、问题正文或 OCR；管理员仍通过后端会话与 CSRF 校验。
