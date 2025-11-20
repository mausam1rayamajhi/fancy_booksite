
CREATE TABLE IF NOT EXISTS logs (
  id              BIGINT AUTO_INCREMENT PRIMARY KEY,
  ts              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  function_name   VARCHAR(120) NOT NULL,
  status          ENUM('success','error') NOT NULL,
  message         TEXT NULL,
  execution_time  DOUBLE NULL,
  http_method     VARCHAR(10) NULL,
  path            VARCHAR(255) NULL,
  user_agent      VARCHAR(255) NULL,
  extra_json      JSON NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
