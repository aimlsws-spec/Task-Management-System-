-- MySQL dump 10.13  Distrib 8.0.46, for Win64 (x86_64)
--
-- Host: localhost    Database: tms
-- ------------------------------------------------------
-- Server version	8.0.46

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `activity_logs`
--

DROP TABLE IF EXISTS `activity_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `activity_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `actor_user_id` bigint DEFAULT NULL,
  `action` varchar(60) NOT NULL,
  `entity_type` varchar(50) NOT NULL,
  `entity_id` varchar(50) NOT NULL,
  `task_id` bigint DEFAULT NULL,
  `before_json` json DEFAULT NULL,
  `after_json` json DEFAULT NULL,
  `ip` varchar(64) DEFAULT NULL,
  `user_agent` varchar(255) DEFAULT NULL,
  `request_id` varchar(64) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_al_action` (`action`,`created_at`),
  KEY `ix_al_actor` (`actor_user_id`,`created_at`),
  KEY `ix_al_entity` (`entity_type`,`entity_id`,`created_at`),
  KEY `ix_al_task` (`task_id`,`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `activity_logs`
--

LOCK TABLES `activity_logs` WRITE;
/*!40000 ALTER TABLE `activity_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `activity_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
INSERT INTO `alembic_version` VALUES ('0013');
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `comment_mentions`
--

DROP TABLE IF EXISTS `comment_mentions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `comment_mentions` (
  `comment_id` bigint NOT NULL,
  `user_id` bigint NOT NULL,
  PRIMARY KEY (`comment_id`,`user_id`),
  KEY `user_id` (`user_id`),
  CONSTRAINT `comment_mentions_ibfk_1` FOREIGN KEY (`comment_id`) REFERENCES `task_comments` (`id`),
  CONSTRAINT `comment_mentions_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `comment_mentions`
--

LOCK TABLES `comment_mentions` WRITE;
/*!40000 ALTER TABLE `comment_mentions` DISABLE KEYS */;
/*!40000 ALTER TABLE `comment_mentions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `deadline_extension_requests`
--

DROP TABLE IF EXISTS `deadline_extension_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `deadline_extension_requests` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `requested_by_user_id` bigint NOT NULL,
  `deadline_version` int NOT NULL,
  `requested_due_at` datetime(6) NOT NULL,
  `reason` text NOT NULL,
  `status` varchar(10) NOT NULL,
  `decided_by_user_id` bigint DEFAULT NULL,
  `decided_at` datetime(6) DEFAULT NULL,
  `decision_note` text,
  `approved_due_at` datetime(6) DEFAULT NULL,
  `deadline_history_id` bigint DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `deadline_history_id` (`deadline_history_id`),
  KEY `decided_by_user_id` (`decided_by_user_id`),
  KEY `requested_by_user_id` (`requested_by_user_id`),
  KEY `ix_er_task` (`task_id`,`status`),
  CONSTRAINT `deadline_extension_requests_ibfk_1` FOREIGN KEY (`deadline_history_id`) REFERENCES `task_deadline_history` (`id`),
  CONSTRAINT `deadline_extension_requests_ibfk_2` FOREIGN KEY (`decided_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `deadline_extension_requests_ibfk_3` FOREIGN KEY (`requested_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `deadline_extension_requests_ibfk_4` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `deadline_extension_requests`
--

LOCK TABLES `deadline_extension_requests` WRITE;
/*!40000 ALTER TABLE `deadline_extension_requests` DISABLE KEYS */;
/*!40000 ALTER TABLE `deadline_extension_requests` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `departments`
--

DROP TABLE IF EXISTS `departments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `departments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(100) NOT NULL,
  `code` varchar(30) NOT NULL,
  `parent_id` bigint DEFAULT NULL,
  `head_employee_id` bigint DEFAULT NULL,
  `is_active` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `is_system` tinyint(1) NOT NULL DEFAULT '0',
  `self_service` tinyint(1) NOT NULL DEFAULT '1',
  `qa_employee_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  UNIQUE KEY `name` (`name`),
  KEY `parent_id` (`parent_id`),
  KEY `fk_dept_head` (`head_employee_id`),
  KEY `fk_dept_qa` (`qa_employee_id`),
  CONSTRAINT `departments_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `fk_dept_head` FOREIGN KEY (`head_employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `fk_dept_qa` FOREIGN KEY (`qa_employee_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `departments`
--

LOCK TABLES `departments` WRITE;
/*!40000 ALTER TABLE `departments` DISABLE KEYS */;
INSERT INTO `departments` VALUES (1,'Management','MGMT',NULL,NULL,1,'2026-11-18 11:03:43.219774',1,0,NULL),(2,'Unassigned','UNASSIGNED',NULL,NULL,1,'2026-11-18 11:03:43.219774',1,0,NULL);
/*!40000 ALTER TABLE `departments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `email_logs`
--

DROP TABLE IF EXISTS `email_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `email_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `notification_id` bigint DEFAULT NULL,
  `to_user_id` bigint DEFAULT NULL,
  `to_email` varchar(255) NOT NULL,
  `subject` varchar(255) NOT NULL,
  `body_text` text NOT NULL,
  `body_html` text NOT NULL,
  `urgent` tinyint(1) NOT NULL,
  `status` varchar(10) NOT NULL,
  `attempts` int NOT NULL,
  `next_attempt_at` datetime(6) NOT NULL,
  `last_error` text,
  `backend` varchar(10) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `sent_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `notification_id` (`notification_id`),
  KEY `to_user_id` (`to_user_id`),
  KEY `ix_email_status` (`status`,`next_attempt_at`),
  CONSTRAINT `email_logs_ibfk_1` FOREIGN KEY (`notification_id`) REFERENCES `notifications` (`id`),
  CONSTRAINT `email_logs_ibfk_2` FOREIGN KEY (`to_user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `email_logs`
--

LOCK TABLES `email_logs` WRITE;
/*!40000 ALTER TABLE `email_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `email_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `employee_leaves`
--

DROP TABLE IF EXISTS `employee_leaves`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `employee_leaves` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `employee_id` bigint NOT NULL,
  `from_date` date NOT NULL,
  `to_date` date NOT NULL,
  `type` varchar(30) NOT NULL,
  `status` varchar(20) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_leave_emp` (`employee_id`,`from_date`,`to_date`),
  CONSTRAINT `employee_leaves_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `employee_leaves`
--

LOCK TABLES `employee_leaves` WRITE;
/*!40000 ALTER TABLE `employee_leaves` DISABLE KEYS */;
/*!40000 ALTER TABLE `employee_leaves` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `employees`
--

DROP TABLE IF EXISTS `employees`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `employees` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `employee_code` varchar(30) NOT NULL,
  `full_name` varchar(150) NOT NULL,
  `phone` varchar(30) DEFAULT NULL,
  `job_title` varchar(100) DEFAULT NULL,
  `department_id` bigint NOT NULL,
  `status` varchar(20) NOT NULL,
  `joined_on` date DEFAULT NULL,
  `left_on` date DEFAULT NULL,
  `daily_capacity_hours` decimal(4,2) NOT NULL,
  `can_receive_tasks` tinyint(1) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `employee_code` (`employee_code`),
  UNIQUE KEY `user_id` (`user_id`),
  KEY `ix_emp_dept_status` (`department_id`,`status`),
  CONSTRAINT `employees_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `employees_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `employees`
--

LOCK TABLES `employees` WRITE;
/*!40000 ALTER TABLE `employees` DISABLE KEYS */;
INSERT INTO `employees` VALUES (1,1,'SW-25BZS3','Administrator',NULL,'System Administrator',1,'active',NULL,NULL,8.50,0,'2026-11-18 11:03:43.359018');
/*!40000 ALTER TABLE `employees` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `holidays`
--

DROP TABLE IF EXISTS `holidays`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `holidays` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `date` date NOT NULL,
  `name` varchar(150) NOT NULL,
  `is_working_override` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `holidays`
--

LOCK TABLES `holidays` WRITE;
/*!40000 ALTER TABLE `holidays` DISABLE KEYS */;
/*!40000 ALTER TABLE `holidays` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `job_failures`
--

DROP TABLE IF EXISTS `job_failures`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `job_failures` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `job` varchar(60) NOT NULL,
  `error` text NOT NULL,
  `context` json DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `job_failures`
--

LOCK TABLES `job_failures` WRITE;
/*!40000 ALTER TABLE `job_failures` DISABLE KEYS */;
/*!40000 ALTER TABLE `job_failures` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `login_otps`
--

DROP TABLE IF EXISTS `login_otps`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `login_otps` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `challenge_hash` varchar(64) NOT NULL,
  `code_hash` varchar(64) NOT NULL,
  `purpose` varchar(10) NOT NULL DEFAULT 'login',
  `expires_at` datetime NOT NULL,
  `attempts` int NOT NULL DEFAULT '0',
  `sends` int NOT NULL DEFAULT '1',
  `last_sent_at` datetime NOT NULL,
  `used_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `challenge_hash` (`challenge_hash`),
  KEY `ix_login_otps_user_id` (`user_id`),
  CONSTRAINT `login_otps_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `login_otps`
--

LOCK TABLES `login_otps` WRITE;
/*!40000 ALTER TABLE `login_otps` DISABLE KEYS */;
/*!40000 ALTER TABLE `login_otps` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `manager_departments`
--

DROP TABLE IF EXISTS `manager_departments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `manager_departments` (
  `employee_id` bigint NOT NULL,
  `department_id` bigint NOT NULL,
  PRIMARY KEY (`employee_id`,`department_id`),
  KEY `department_id` (`department_id`),
  CONSTRAINT `manager_departments_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `manager_departments_ibfk_2` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `manager_departments`
--

LOCK TABLES `manager_departments` WRITE;
/*!40000 ALTER TABLE `manager_departments` DISABLE KEYS */;
/*!40000 ALTER TABLE `manager_departments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notification_preferences`
--

DROP TABLE IF EXISTS `notification_preferences`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notification_preferences` (
  `user_id` bigint NOT NULL,
  `event_type` varchar(60) NOT NULL,
  `channel` varchar(10) NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  PRIMARY KEY (`user_id`,`event_type`,`channel`),
  CONSTRAINT `notification_preferences_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notification_preferences`
--

LOCK TABLES `notification_preferences` WRITE;
/*!40000 ALTER TABLE `notification_preferences` DISABLE KEYS */;
/*!40000 ALTER TABLE `notification_preferences` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notification_rules`
--

DROP TABLE IF EXISTS `notification_rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notification_rules` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `event_type` varchar(60) NOT NULL,
  `selector` varchar(60) NOT NULL,
  `channels` varchar(20) NOT NULL,
  `mandatory` tinyint(1) NOT NULL,
  `urgent` tinyint(1) NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `condition_json` json DEFAULT NULL,
  `note` varchar(200) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_nr_event` (`event_type`,`enabled`)
) ENGINE=InnoDB AUTO_INCREMENT=173 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notification_rules`
--

LOCK TABLES `notification_rules` WRITE;
/*!40000 ALTER TABLE `notification_rules` DISABLE KEYS */;
INSERT INTO `notification_rules` VALUES (1,'TASK_CREATED','ASSIGNEE','in_app,email',1,0,1,'null',NULL),(2,'TASK_CREATED','DIRECT_MANAGER','in_app,email',0,0,1,'null',NULL),(3,'TASK_CREATED','DEPARTMENT_HEAD','in_app,email',0,0,1,'null',NULL),(4,'TASK_CREATED','ANCESTOR_ROLE:manager','in_app,email',0,0,1,'null',NULL),(5,'TASK_CREATED','ROLE:ceo','in_app,email',0,0,1,'{\"assigner_role\": [\"owner\"]}',NULL),(6,'TASK_CREATED','ROLE:ceo','in_app',0,0,0,'{\"assigner_role\": [\"manager\", \"department_head\"]}',NULL),(7,'TASK_CREATED','ROLE:owner','in_app',0,0,0,'{\"assigner_role\": [\"manager\", \"department_head\", \"ceo\"]}',NULL),(8,'TASK_CREATED','ACTOR','in_app',0,0,0,'null',NULL),(9,'TASK_CREATED','ROLE:ceo','in_app,email',0,0,1,'{\"assignee_role\": [\"department_head\"], \"assigner_role\": [\"department_head\"]}',NULL),(10,'TASK_CREATED','ROLE:owner','in_app',0,0,1,'{\"assignee_role\": [\"department_head\"], \"assigner_role\": [\"department_head\"]}',NULL),(11,'PROJECT_HEAD_NAMED','TARGET_USER','in_app,email',1,0,1,'null',NULL),(12,'PROJECT_MEMBER_ADDED','TARGET_USER','in_app,email',0,0,1,'null',NULL),(13,'PROJECT_CREATED','ROLE:ceo','in_app,email',0,0,1,'null',NULL),(14,'PROJECT_CREATED','ROLE:owner','in_app,email',0,0,1,'null',NULL),(15,'PROJECT_DEADLINE_TOMORROW','PROJECT_PEOPLE','in_app,email',1,0,1,'null',NULL),(16,'PROJECT_DEADLINE_TODAY','PROJECT_PEOPLE','in_app,email',1,1,1,'null',NULL),(17,'PROJECT_OVERDUE','PROJECT_PEOPLE','in_app,email',1,1,1,'null',NULL),(18,'PROJECT_OVERDUE','ROLE:ceo','in_app,email',1,1,1,'null',NULL),(19,'PROJECT_OVERDUE','ROLE:owner','in_app,email',1,1,1,'null',NULL),(20,'PROJECT_TASK_ASSIGNED','PROJECT_HEAD','in_app,email',1,0,1,'null',NULL),(21,'TASK_HEAD_REVIEW_NEEDED','PROJECT_HEAD','in_app,email',1,1,1,'null',NULL),(22,'TASK_HEAD_APPROVED','ASSIGNEE','in_app',0,0,1,'null',NULL),(23,'PROJECT_QA_NAMED','TARGET_USER','in_app,email',1,0,1,'null',NULL),(24,'TASK_QA_ASSIGNED','TASK_QA','in_app,email',1,0,1,'null',NULL),(25,'TASK_QA_REVIEW_NEEDED','TASK_QA','in_app,email',1,1,1,'null',NULL),(26,'TASK_CREATED','TASK_LOOP','in_app,email',0,0,1,'null',NULL),(27,'TASK_QA_APPROVED','ASSIGNEE','in_app',0,0,1,'null',NULL),(28,'TASK_QA_APPROVED','TASK_LOOP','in_app',0,0,1,'null',NULL),(29,'TASK_REVIEW_REJECTED','TASK_LOOP','in_app,email',0,0,1,'null',NULL),(30,'TASK_REVIEW_APPROVED','TASK_LOOP','in_app,email',0,0,1,'null',NULL),(31,'TASK_SUBMITTED','TASK_LOOP','in_app',0,0,1,'null',NULL),(32,'TASK_LEADERSHIP_REVIEW_NEEDED','ROLE:ceo','in_app,email',1,1,1,'null',NULL),(33,'TASK_LEADERSHIP_REVIEW_NEEDED','ROLE:owner','in_app,email',1,1,1,'null',NULL),(34,'PROJECT_READY_FOR_REVIEW','ROLE:ceo','in_app,email',1,1,1,'null',NULL),(35,'PROJECT_READY_FOR_REVIEW','ROLE:owner','in_app,email',1,1,1,'null',NULL),(36,'PROJECT_COMPLETED','PROJECT_HEAD','in_app,email',0,0,1,'null',NULL),(37,'PROJECT_COMPLETED','PROJECT_MEMBERS','in_app',0,0,1,'null',NULL),(38,'EMPLOYEE_SIGNED_UP','ROLE:owner','in_app,email',1,0,1,'null',NULL),(39,'EMPLOYEE_SIGNED_UP','ROLE:admin','in_app,email',1,0,1,'null',NULL),(40,'TASK_OWNERSHIP_TAKEN','ASSIGNEE','in_app',0,0,1,'null',NULL),(41,'TASK_OWNERSHIP_TAKEN','ASSIGNER','in_app',0,0,1,'null',NULL),(42,'TASK_OWNERSHIP_TAKEN','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(43,'TASK_OWNERSHIP_TAKEN','ANCESTOR_ROLE:manager','in_app',0,0,1,'null',NULL),(44,'TASK_REASSIGNED','ASSIGNEE','in_app,email',1,0,1,'null',NULL),(45,'TASK_REASSIGNED','PREVIOUS_ASSIGNEE','in_app',1,0,1,'null',NULL),(46,'TASK_REASSIGNED','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(47,'TASK_REASSIGNED','DEPARTMENT_HEAD','in_app',0,0,1,'null',NULL),(48,'TASK_ACKNOWLEDGED','ASSIGNER','in_app',0,0,1,'null',NULL),(49,'TASK_ACKNOWLEDGED','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(50,'TASK_ACKNOWLEDGED','ROLE:ceo','in_app',0,0,0,'null',NULL),(51,'TASK_ACKNOWLEDGED','ROLE:owner','in_app',0,0,0,'null',NULL),(52,'TASK_STARTED','ASSIGNER','in_app',0,0,1,'null',NULL),(53,'TASK_STARTED','DIRECT_MANAGER','in_app',0,0,0,'null',NULL),(54,'TASK_PROGRESS','ASSIGNER','in_app',0,0,1,'null',NULL),(55,'TASK_PROGRESS','DIRECT_MANAGER','in_app',0,0,0,'null',NULL),(56,'TASK_PRIORITY_CHANGED','ASSIGNEE','in_app,email',1,0,1,'null',NULL),(57,'TASK_PRIORITY_CHANGED','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(58,'TASK_ON_HOLD','ASSIGNEE','in_app',0,0,1,'null',NULL),(59,'TASK_ON_HOLD','ASSIGNER','in_app',0,0,1,'null',NULL),(60,'TASK_RESUMED_FROM_HOLD','ASSIGNEE','in_app',0,0,1,'null',NULL),(61,'TASK_COMPLETED','ASSIGNER','in_app,email',0,0,1,'null',NULL),(62,'TASK_COMPLETED','DIRECT_MANAGER','in_app,email',0,0,1,'null',NULL),(63,'TASK_COMPLETED','DEPARTMENT_HEAD','in_app',0,0,1,'null',NULL),(64,'TASK_COMPLETED','ACTOR','in_app',0,0,1,'null',NULL),(65,'TASK_COMPLETED','ROLE:ceo','in_app',0,0,0,'null',NULL),(66,'TASK_COMPLETED','ROLE:owner','in_app',0,0,0,'null',NULL),(67,'TASK_SUBMITTED','DIRECT_MANAGER','in_app,email',0,0,1,'null',NULL),(68,'TASK_SUBMITTED','DEPARTMENT_HEAD','in_app,email',0,0,1,'null',NULL),(69,'TASK_SUBMITTED','ASSIGNER','in_app,email',0,0,1,'null',NULL),(70,'TASK_SUBMITTED','ACTOR','in_app',0,0,1,'null',NULL),(71,'TASK_REVIEW_APPROVED','ASSIGNEE','in_app,email',1,0,1,'null',NULL),(72,'TASK_REVIEW_REJECTED','ASSIGNEE','in_app,email',1,1,1,'null',NULL),(73,'TASK_VERIFIED','ASSIGNEE','in_app',0,0,1,'null',NULL),(74,'TASK_REVERTED','ASSIGNEE','in_app,email',1,1,1,'null',NULL),(75,'TASK_REVERTED','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(76,'TASK_REVERTED','ASSIGNER','in_app',0,0,1,'null',NULL),(77,'TASK_CANCELLED','ASSIGNEE','in_app,email',1,1,1,'null',NULL),(78,'TASK_CANCELLED','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(79,'TASK_CANCELLED','ASSIGNER','in_app',0,0,1,'null',NULL),(80,'TASK_DEADLINE_CHANGED','ASSIGNEE','in_app,email',1,1,1,'null',NULL),(81,'TASK_DEADLINE_CHANGED','DIRECT_MANAGER','in_app,email',1,1,1,'null',NULL),(82,'TASK_DEADLINE_CHANGED','DEPARTMENT_HEAD','in_app,email',1,1,1,'null',NULL),(83,'TASK_DEADLINE_CHANGED','ROLE:ceo','in_app,email',1,1,1,'null',NULL),(84,'TASK_DEADLINE_CHANGED','ROLE:owner','in_app,email',1,1,1,'null',NULL),(85,'DELAY_EXPLANATION_SUBMITTED','ACTOR','in_app',0,0,1,'null',NULL),(86,'DELAY_EXPLANATION_SUBMITTED','DIRECT_MANAGER','in_app,email',0,0,1,'null',NULL),(87,'DELAY_EXPLANATION_SUBMITTED','DEPARTMENT_HEAD','in_app,email',0,0,1,'null',NULL),(88,'DELAY_EXPLANATION_SUBMITTED','ANCESTOR_ROLE:manager','in_app,email',0,0,1,'null',NULL),(89,'DELAY_RELEASED','ROLE:ceo','in_app,email',0,0,1,'null',NULL),(90,'DELAY_RELEASED','ROLE:owner','in_app,email',0,0,1,'null',NULL),(91,'DELAY_RELEASED','ASSIGNER','in_app',0,0,1,'null',NULL),(92,'EXTENSION_REQUESTED','DIRECT_MANAGER','in_app,email',0,0,1,'null',NULL),(93,'EXTENSION_REQUESTED','DEPARTMENT_HEAD','in_app,email',0,0,1,'null',NULL),(94,'EXTENSION_REQUESTED','ASSIGNER','in_app',0,0,1,'null',NULL),(95,'EXTENSION_REQUESTED','ANCESTOR_ROLE:manager','in_app',0,0,1,'null',NULL),(96,'EXTENSION_REQUESTED','ACTOR','in_app',0,0,1,'null',NULL),(97,'EXTENSION_DECIDED','ASSIGNEE','in_app,email',1,1,1,'null',NULL),(98,'DELAY_EXPLANATION_SUBMITTED','ASSIGNER','in_app',0,0,1,'{\"assigner_role\": [\"manager\", \"department_head\"]}',NULL),(99,'DELAY_REVIEWED','ASSIGNEE','in_app,email',1,0,1,'null',NULL),(100,'TASK_REMINDER_24H','ASSIGNEE','in_app,email',1,0,1,'null',NULL),(101,'TASK_REMINDER_2H','ASSIGNEE','in_app,email',1,1,1,'null',NULL),(102,'TASK_OVERDUE','ASSIGNEE','in_app,email',1,1,1,'null',NULL),(103,'TASK_OVERDUE','DIRECT_MANAGER','in_app,email',1,1,1,'null',NULL),(104,'TASK_OVERDUE','DEPARTMENT_HEAD','in_app,email',1,1,1,'null',NULL),(105,'TASK_OVERDUE','ANCESTOR_ROLE:manager','in_app,email',1,1,1,'null',NULL),(106,'TASK_OVERDUE','ROLE:ceo','in_app,email',1,1,1,'null',NULL),(107,'TASK_OVERDUE','ROLE:owner','in_app,email',1,1,1,'null',NULL),(108,'TASK_ESCALATION_1','ASSIGNEE','in_app,email',1,1,1,'null',NULL),(109,'TASK_ESCALATION_2','DIRECT_MANAGER','in_app,email',1,1,1,'null',NULL),(110,'TASK_ESCALATION_2','DEPARTMENT_HEAD','in_app,email',1,1,1,'null',NULL),(111,'TASK_ESCALATION_2','ANCESTOR_ROLE:manager','in_app,email',1,1,1,'null',NULL),(112,'TASK_ESCALATION_2','ROLE:ceo','in_app,email',1,1,1,'null',NULL),(113,'TASK_ESCALATION_2','ASSIGNEE','in_app',1,0,1,'null',NULL),(114,'TASK_ESCALATION_3','DIRECT_MANAGER','in_app,email',1,1,1,'null',NULL),(115,'TASK_ESCALATION_3','DEPARTMENT_HEAD','in_app,email',1,1,1,'null',NULL),(116,'TASK_ESCALATION_3','ANCESTOR_ROLE:manager','in_app,email',1,1,1,'null',NULL),(117,'TASK_ESCALATION_3','ROLE:ceo','in_app,email',1,1,1,'null',NULL),(118,'TASK_ESCALATION_3','ROLE:owner','in_app,email',1,1,1,'null',NULL),(119,'TASK_ESCALATION_3','ASSIGNEE','in_app',1,0,1,'null',NULL),(120,'TIMER_CHECKIN','ASSIGNEE','in_app',1,0,1,'null',NULL),(121,'TIMER_AUTO_CLOSED','ASSIGNEE','in_app,email',1,0,1,'null',NULL),(122,'TIME_CORRECTION_REQUESTED','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(123,'TIME_CORRECTION_REQUESTED','DEPARTMENT_HEAD','in_app',0,0,1,'null',NULL),(124,'TIME_CORRECTION_REQUESTED','ANCESTOR_ROLE:manager','in_app',0,0,1,'null',NULL),(125,'TIME_CORRECTION_APPROVED','ASSIGNEE','in_app',1,0,1,'null',NULL),(126,'TIME_CORRECTION_REJECTED','ASSIGNEE','in_app',1,0,1,'null',NULL),(127,'TIME_LOG_ADJUSTED','ASSIGNEE','in_app',0,0,1,'null',NULL),(128,'TIME_UNCONFIRMED_3D','DIRECT_MANAGER','in_app,email',0,0,1,'null',NULL),(129,'TIME_UNCONFIRMED_3D','DEPARTMENT_HEAD','in_app',0,0,1,'null',NULL),(130,'BLOCKER_RAISED','ACTOR','in_app',0,0,1,'null',NULL),(131,'BLOCKER_RAISED','DIRECT_MANAGER','in_app,email',0,1,1,'null',NULL),(132,'BLOCKER_RAISED','DEPARTMENT_HEAD','in_app,email',0,1,1,'null',NULL),(133,'BLOCKER_RAISED','ANCESTOR_ROLE:manager','in_app,email',0,1,1,'null',NULL),(134,'BLOCKER_RAISED','ASSIGNER','in_app',0,0,1,'null',NULL),(135,'BLOCKER_RAISED','ROLE:ceo','in_app,email',0,1,1,'{\"priority\": [\"critical\"]}',NULL),(136,'BLOCKER_RAISED','ROLE:owner','in_app,email',0,1,1,'{\"priority\": [\"critical\"]}',NULL),(137,'BLOCKER_ACKNOWLEDGED','BLOCKER_RAISER','in_app',1,0,1,'null',NULL),(138,'BLOCKER_ASSIGNED','BLOCKER_OWNER','in_app,email',1,0,1,'null',NULL),(139,'BLOCKER_ASSIGNED','BLOCKER_RAISER','in_app',0,0,1,'null',NULL),(140,'BLOCKER_IN_PROGRESS','BLOCKER_RAISER','in_app',0,0,1,'null',NULL),(141,'BLOCKER_REPLIED','BLOCKER_RAISER','in_app,email',0,0,1,'null',NULL),(142,'BLOCKER_REPLIED','BLOCKER_OWNER','in_app',0,0,1,'null',NULL),(143,'BLOCKER_REPLIED','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(144,'BLOCKER_RESOLVED','BLOCKER_RAISER','in_app,email',1,0,1,'null',NULL),(145,'BLOCKER_RESOLVED','DIRECT_MANAGER','in_app,email',0,0,1,'null',NULL),(146,'BLOCKER_RESOLVED','ASSIGNER','in_app',0,0,1,'null',NULL),(147,'BLOCKER_RESOLVED','ROLE:ceo','in_app',0,0,0,'null',NULL),(148,'BLOCKER_RESOLVED','ROLE:owner','in_app',0,0,0,'null',NULL),(149,'BLOCKER_CLOSED','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(150,'BLOCKER_CLOSED','BLOCKER_OWNER','in_app',0,0,1,'null',NULL),(151,'BLOCKER_REOPENED','DIRECT_MANAGER','in_app,email',0,1,1,'null',NULL),(152,'BLOCKER_REOPENED','DEPARTMENT_HEAD','in_app,email',0,1,1,'null',NULL),(153,'BLOCKER_REOPENED','BLOCKER_OWNER','in_app',0,0,1,'null',NULL),(154,'BLOCKER_ESCALATED','DEPARTMENT_HEAD','in_app,email',1,1,1,'null',NULL),(155,'BLOCKER_ESCALATED','ANCESTOR_ROLE:manager','in_app,email',1,1,1,'null',NULL),(156,'BLOCKER_ESCALATED','ROLE:ceo','in_app,email',1,1,1,'null',NULL),(157,'BLOCKER_ESCALATED','ROLE:owner','in_app,email',1,1,1,'null',NULL),(158,'BLOCKER_ESCALATED','BLOCKER_RAISER','in_app',0,0,1,'null',NULL),(159,'COMMENT_ADDED','MENTIONED','in_app,email',0,0,1,'null',NULL),(160,'COMMENT_ADDED','COMMENT_PARENT_AUTHOR','in_app',0,0,1,'null',NULL),(161,'COMMENT_ADDED','ASSIGNEE','in_app',0,0,1,'null',NULL),(162,'COMMENT_ADDED','ASSIGNER','in_app',0,0,1,'null',NULL),(163,'COMMENT_ADDED','TASK_LOOP','in_app,email',1,0,1,'null',NULL),(164,'QUESTION_ASKED','TASK_LOOP','in_app,email',1,0,1,'null',NULL),(165,'BLOCKER_RAISED','TASK_LOOP','in_app,email',0,0,1,'null',NULL),(166,'BLOCKER_REPLIED','TASK_LOOP','in_app,email',0,0,1,'null',NULL),(167,'BLOCKER_RESOLVED','TASK_LOOP','in_app,email',0,0,1,'null',NULL),(168,'QUESTION_ASKED','MENTIONED','in_app,email',0,0,1,'null',NULL),(169,'QUESTION_ASKED','ASSIGNER','in_app,email',0,0,1,'null',NULL),(170,'QUESTION_ASKED','DIRECT_MANAGER','in_app',0,0,1,'null',NULL),(171,'QUESTION_ASKED','DEPARTMENT_HEAD','in_app',0,0,1,'null',NULL),(172,'QUESTION_ASKED','ASSIGNEE','in_app',0,0,1,'null',NULL);
/*!40000 ALTER TABLE `notification_rules` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `notifications`
--

DROP TABLE IF EXISTS `notifications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `notifications` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `event_type` varchar(60) NOT NULL,
  `title` varchar(200) NOT NULL,
  `body` text NOT NULL,
  `task_id` bigint DEFAULT NULL,
  `reasons` json DEFAULT NULL,
  `dedupe_key` varchar(160) NOT NULL,
  `urgent` tinyint(1) NOT NULL,
  `is_read` tinyint(1) NOT NULL,
  `read_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_notification_dedupe` (`user_id`,`dedupe_key`),
  KEY `ix_notif_user` (`user_id`,`is_read`,`created_at`),
  CONSTRAINT `notifications_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `notifications`
--

LOCK TABLES `notifications` WRITE;
/*!40000 ALTER TABLE `notifications` DISABLE KEYS */;
/*!40000 ALTER TABLE `notifications` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `outbox_events`
--

DROP TABLE IF EXISTS `outbox_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `outbox_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `event_type` varchar(60) NOT NULL,
  `task_id` bigint DEFAULT NULL,
  `actor_user_id` bigint DEFAULT NULL,
  `payload` json DEFAULT NULL,
  `dedupe_key` varchar(160) DEFAULT NULL,
  `status` varchar(10) NOT NULL,
  `attempts` int NOT NULL,
  `last_error` text,
  `created_at` datetime(6) NOT NULL,
  `processed_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_outbox_dedupe` (`dedupe_key`),
  KEY `ix_outbox_status` (`status`,`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `outbox_events`
--

LOCK TABLES `outbox_events` WRITE;
/*!40000 ALTER TABLE `outbox_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `outbox_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `password_reset_tokens`
--

DROP TABLE IF EXISTS `password_reset_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `password_reset_tokens` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `token_hash` varchar(64) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `used_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token_hash` (`token_hash`),
  KEY `ix_password_reset_tokens_user_id` (`user_id`),
  CONSTRAINT `password_reset_tokens_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `password_reset_tokens`
--

LOCK TABLES `password_reset_tokens` WRITE;
/*!40000 ALTER TABLE `password_reset_tokens` DISABLE KEYS */;
/*!40000 ALTER TABLE `password_reset_tokens` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `permissions`
--

DROP TABLE IF EXISTS `permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `permissions` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `code` varchar(80) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  `category` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=30 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `permissions`
--

LOCK TABLES `permissions` WRITE;
/*!40000 ALTER TABLE `permissions` DISABLE KEYS */;
INSERT INTO `permissions` VALUES (1,'task.view','View tasks','task'),(2,'task.create','Create tasks','task'),(3,'task.assign','Assign tasks to employees','task'),(4,'task.edit','Edit task fields','task'),(5,'task.reassign','Reassign tasks','task'),(6,'task.priority.change','Change priority','task'),(7,'task.deadline.edit','Edit / extend deadlines','task'),(8,'task.verify','Verify or revert completed tasks','task'),(9,'task.cancel','Cancel tasks','task'),(10,'time.view','View time logs','time'),(11,'time.correct.approve','Approve time corrections','time'),(12,'delay.view','View delay explanations','delay'),(13,'delay.review','Review delay explanations','delay'),(14,'blocker.view','View blockers','blocker'),(15,'blocker.raise','Raise blockers','blocker'),(16,'blocker.manage','Resolve / assign / escalate blockers','blocker'),(17,'comment.create','Comment on tasks','comment'),(18,'report.view','View reports','report'),(19,'report.export','Export reports','report'),(20,'dashboard.view','View dashboard','dashboard'),(21,'employee.view','View employees','org'),(22,'employee.manage','Create / edit / deactivate employees','org'),(23,'department.manage','Add, edit, delete departments and set heads','org'),(24,'hierarchy.manage','Manage reporting relationships','org'),(25,'role.manage','Manage roles and permissions','admin'),(26,'project.manage','Manage projects','project'),(27,'settings.manage','System settings, calendar, sign-up rules','admin'),(28,'audit.view','View audit log','admin'),(29,'notification.rules.manage','Manage notification and reminder rules','admin');
/*!40000 ALTER TABLE `permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_members`
--

DROP TABLE IF EXISTS `project_members`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_members` (
  `project_id` bigint NOT NULL,
  `employee_id` bigint NOT NULL,
  PRIMARY KEY (`project_id`,`employee_id`),
  KEY `employee_id` (`employee_id`),
  CONSTRAINT `project_members_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `project_members_ibfk_2` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_members`
--

LOCK TABLES `project_members` WRITE;
/*!40000 ALTER TABLE `project_members` DISABLE KEYS */;
/*!40000 ALTER TABLE `project_members` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `project_points`
--

DROP TABLE IF EXISTS `project_points`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `project_points` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `project_id` bigint NOT NULL,
  `title` varchar(200) NOT NULL,
  `details` text,
  `expected_result` text,
  `position` int NOT NULL,
  `task_id` bigint DEFAULT NULL,
  `created_by_user_id` bigint DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `is_done` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `task_id` (`task_id`),
  KEY `created_by_user_id` (`created_by_user_id`),
  KEY `ix_point_project` (`project_id`,`position`),
  CONSTRAINT `project_points_ibfk_1` FOREIGN KEY (`created_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `project_points_ibfk_2` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`),
  CONSTRAINT `project_points_ibfk_3` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `project_points`
--

LOCK TABLES `project_points` WRITE;
/*!40000 ALTER TABLE `project_points` DISABLE KEYS */;
/*!40000 ALTER TABLE `project_points` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `projects`
--

DROP TABLE IF EXISTS `projects`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `projects` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `code` varchar(30) NOT NULL,
  `name` varchar(150) NOT NULL,
  `description` text,
  `department_id` bigint DEFAULT NULL,
  `owner_employee_id` bigint DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `starts_on` date DEFAULT NULL,
  `ends_on` date DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `expected_result` text,
  `head_employee_id` bigint DEFAULT NULL,
  `completed_at` datetime(6) DEFAULT NULL,
  `reviewed_by_user_id` bigint DEFAULT NULL,
  `review_note` text,
  `qa_employee_id` bigint DEFAULT NULL,
  `assignee_id` bigint DEFAULT NULL,
  `progress_pct` smallint NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`),
  KEY `department_id` (`department_id`),
  KEY `owner_employee_id` (`owner_employee_id`),
  KEY `fk_project_head` (`head_employee_id`),
  KEY `fk_project_reviewer` (`reviewed_by_user_id`),
  KEY `fk_project_qa` (`qa_employee_id`),
  KEY `fk_project_assignee` (`assignee_id`),
  CONSTRAINT `fk_project_assignee` FOREIGN KEY (`assignee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `fk_project_head` FOREIGN KEY (`head_employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `fk_project_qa` FOREIGN KEY (`qa_employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `fk_project_reviewer` FOREIGN KEY (`reviewed_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `projects_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `projects_ibfk_2` FOREIGN KEY (`owner_employee_id`) REFERENCES `employees` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `projects`
--

LOCK TABLES `projects` WRITE;
/*!40000 ALTER TABLE `projects` DISABLE KEYS */;
/*!40000 ALTER TABLE `projects` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `refresh_tokens`
--

DROP TABLE IF EXISTS `refresh_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `refresh_tokens` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint NOT NULL,
  `family_id` varchar(36) NOT NULL,
  `token_hash` varchar(64) NOT NULL,
  `expires_at` datetime(6) NOT NULL,
  `revoked_at` datetime(6) DEFAULT NULL,
  `replaced_by_id` bigint DEFAULT NULL,
  `ip` varchar(64) DEFAULT NULL,
  `user_agent` varchar(255) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `token_hash` (`token_hash`),
  KEY `ix_refresh_family` (`family_id`),
  KEY `ix_refresh_user` (`user_id`),
  CONSTRAINT `refresh_tokens_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `refresh_tokens`
--

LOCK TABLES `refresh_tokens` WRITE;
/*!40000 ALTER TABLE `refresh_tokens` DISABLE KEYS */;
/*!40000 ALTER TABLE `refresh_tokens` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `reminder_log`
--

DROP TABLE IF EXISTS `reminder_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `reminder_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `rule_id` bigint NOT NULL,
  `deadline_version` int NOT NULL,
  `assignee_id` bigint NOT NULL,
  `fired_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_reminder_once` (`task_id`,`rule_id`,`deadline_version`,`assignee_id`),
  KEY `assignee_id` (`assignee_id`),
  KEY `rule_id` (`rule_id`),
  CONSTRAINT `reminder_log_ibfk_1` FOREIGN KEY (`assignee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `reminder_log_ibfk_2` FOREIGN KEY (`rule_id`) REFERENCES `reminder_rules` (`id`),
  CONSTRAINT `reminder_log_ibfk_3` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `reminder_log`
--

LOCK TABLES `reminder_log` WRITE;
/*!40000 ALTER TABLE `reminder_log` DISABLE KEYS */;
/*!40000 ALTER TABLE `reminder_log` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `reminder_rules`
--

DROP TABLE IF EXISTS `reminder_rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `reminder_rules` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `code` varchar(30) NOT NULL,
  `kind` varchar(20) NOT NULL,
  `minutes` int NOT NULL,
  `working_days` int NOT NULL,
  `event_type` varchar(60) NOT NULL,
  `statuses` varchar(200) NOT NULL,
  `enabled` tinyint(1) NOT NULL,
  `sort_order` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `reminder_rules`
--

LOCK TABLES `reminder_rules` WRITE;
/*!40000 ALTER TABLE `reminder_rules` DISABLE KEYS */;
INSERT INTO `reminder_rules` VALUES (1,'before_24h','before',1440,0,'TASK_REMINDER_24H','assigned,acknowledged,in_progress,blocked,reopened',1,10),(2,'before_2h','before',120,0,'TASK_REMINDER_2H','assigned,acknowledged,in_progress,blocked,reopened',1,20),(3,'at_due','at_due',0,0,'TASK_OVERDUE','assigned,acknowledged,in_progress,blocked,reopened',1,30),(4,'after_1d','after_working_days',0,1,'TASK_ESCALATION_1','assigned,acknowledged,in_progress,blocked,reopened',1,40),(5,'after_3d','after_working_days',0,3,'TASK_ESCALATION_2','assigned,acknowledged,in_progress,blocked,reopened',1,50),(6,'after_7d','after_working_days',0,7,'TASK_ESCALATION_3','assigned,acknowledged,in_progress,blocked,reopened',1,60);
/*!40000 ALTER TABLE `reminder_rules` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `reporting_relationships`
--

DROP TABLE IF EXISTS `reporting_relationships`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `reporting_relationships` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `employee_id` bigint NOT NULL,
  `reports_to_id` bigint NOT NULL,
  `relation_type` varchar(20) NOT NULL,
  `effective_from` datetime(6) NOT NULL,
  `effective_to` datetime(6) DEFAULT NULL,
  `created_by` bigint DEFAULT NULL,
  `active_flag` int GENERATED ALWAYS AS ((case when (`effective_to` is null) then 1 end)) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rr_one_active` (`employee_id`,`relation_type`,`active_flag`),
  KEY `created_by` (`created_by`),
  KEY `ix_rr_boss` (`reports_to_id`,`effective_to`),
  KEY `ix_rr_emp` (`employee_id`,`effective_to`),
  CONSTRAINT `reporting_relationships_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`),
  CONSTRAINT `reporting_relationships_ibfk_2` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `reporting_relationships_ibfk_3` FOREIGN KEY (`reports_to_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `ck_rr_not_self` CHECK ((`employee_id` <> `reports_to_id`))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `reporting_relationships`
--

LOCK TABLES `reporting_relationships` WRITE;
/*!40000 ALTER TABLE `reporting_relationships` DISABLE KEYS */;
/*!40000 ALTER TABLE `reporting_relationships` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_invites`
--

DROP TABLE IF EXISTS `role_invites`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `role_invites` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `role_id` bigint NOT NULL,
  `created_by` bigint NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `claimed_user_id` bigint DEFAULT NULL,
  `claimed_at` datetime(6) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`),
  KEY `claimed_user_id` (`claimed_user_id`),
  KEY `created_by` (`created_by`),
  KEY `role_id` (`role_id`),
  CONSTRAINT `role_invites_ibfk_1` FOREIGN KEY (`claimed_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `role_invites_ibfk_2` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`),
  CONSTRAINT `role_invites_ibfk_3` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_invites`
--

LOCK TABLES `role_invites` WRITE;
/*!40000 ALTER TABLE `role_invites` DISABLE KEYS */;
/*!40000 ALTER TABLE `role_invites` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `role_permissions`
--

DROP TABLE IF EXISTS `role_permissions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `role_permissions` (
  `role_id` bigint NOT NULL,
  `permission_id` bigint NOT NULL,
  `scope` varchar(20) NOT NULL,
  PRIMARY KEY (`role_id`,`permission_id`),
  KEY `permission_id` (`permission_id`),
  CONSTRAINT `role_permissions_ibfk_1` FOREIGN KEY (`permission_id`) REFERENCES `permissions` (`id`),
  CONSTRAINT `role_permissions_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`),
  CONSTRAINT `ck_rp_scope` CHECK ((`scope` in (_utf8mb4'self',_utf8mb4'team',_utf8mb4'department',_utf8mb4'organization')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `role_permissions`
--

LOCK TABLES `role_permissions` WRITE;
/*!40000 ALTER TABLE `role_permissions` DISABLE KEYS */;
INSERT INTO `role_permissions` VALUES (1,20,'self'),(1,21,'organization'),(1,22,'organization'),(1,23,'organization'),(1,24,'organization'),(1,25,'organization'),(1,27,'organization'),(1,28,'organization'),(1,29,'organization'),(2,1,'organization'),(2,2,'organization'),(2,3,'organization'),(2,4,'organization'),(2,5,'organization'),(2,6,'organization'),(2,7,'organization'),(2,8,'organization'),(2,9,'organization'),(2,10,'organization'),(2,11,'organization'),(2,12,'organization'),(2,13,'organization'),(2,14,'organization'),(2,15,'organization'),(2,16,'organization'),(2,17,'organization'),(2,18,'organization'),(2,19,'organization'),(2,20,'organization'),(2,21,'organization'),(2,26,'organization'),(3,1,'organization'),(3,2,'organization'),(3,3,'organization'),(3,4,'organization'),(3,5,'organization'),(3,6,'organization'),(3,7,'organization'),(3,8,'organization'),(3,9,'organization'),(3,10,'organization'),(3,11,'organization'),(3,12,'organization'),(3,13,'organization'),(3,14,'organization'),(3,15,'organization'),(3,16,'organization'),(3,17,'organization'),(3,18,'organization'),(3,19,'organization'),(3,20,'organization'),(3,21,'organization'),(3,26,'organization'),(4,1,'team'),(4,2,'team'),(4,3,'team'),(4,4,'team'),(4,5,'team'),(4,6,'team'),(4,7,'team'),(4,8,'team'),(4,9,'team'),(4,10,'team'),(4,11,'team'),(4,12,'team'),(4,13,'team'),(4,14,'team'),(4,15,'team'),(4,16,'team'),(4,17,'team'),(4,18,'team'),(4,19,'team'),(4,20,'team'),(4,21,'team'),(4,26,'team'),(5,1,'department'),(5,2,'department'),(5,3,'department'),(5,4,'department'),(5,5,'department'),(5,6,'department'),(5,7,'department'),(5,8,'department'),(5,9,'department'),(5,10,'department'),(5,11,'department'),(5,12,'department'),(5,13,'department'),(5,14,'department'),(5,15,'department'),(5,16,'department'),(5,17,'department'),(5,18,'department'),(5,19,'department'),(5,20,'department'),(5,21,'department'),(5,26,'department'),(6,1,'self'),(6,10,'self'),(6,12,'self'),(6,14,'self'),(6,15,'self'),(6,17,'self'),(6,18,'self'),(6,19,'self'),(6,20,'self'),(6,21,'self');
/*!40000 ALTER TABLE `role_permissions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `roles`
--

DROP TABLE IF EXISTS `roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `roles` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `code` varchar(50) NOT NULL,
  `name` varchar(100) NOT NULL,
  `rank` smallint NOT NULL,
  `is_system` tinyint(1) NOT NULL,
  `description` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `code` (`code`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `roles`
--

LOCK TABLES `roles` WRITE;
/*!40000 ALTER TABLE `roles` DISABLE KEYS */;
INSERT INTO `roles` VALUES (1,'admin','Admin',110,1,'System administrator: organization setup only, no task authority'),(2,'owner','Owner',100,1,'Highest business authority, organization-wide task control'),(3,'ceo','CEO',90,1,'Senior management, organization-wide visibility'),(4,'manager','Manager',70,1,'Supervises employees and department heads'),(5,'department_head','Department Head',50,1,'Runs a department'),(6,'employee','Employee',10,1,'Works on assigned tasks');
/*!40000 ALTER TABLE `roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `system_settings`
--

DROP TABLE IF EXISTS `system_settings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `system_settings` (
  `key` varchar(100) NOT NULL,
  `value` json DEFAULT NULL,
  `updated_by` bigint DEFAULT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`key`),
  KEY `updated_by` (`updated_by`),
  CONSTRAINT `system_settings_ibfk_1` FOREIGN KEY (`updated_by`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `system_settings`
--

LOCK TABLES `system_settings` WRITE;
/*!40000 ALTER TABLE `system_settings` DISABLE KEYS */;
INSERT INTO `system_settings` VALUES ('notification_rules_version','5',NULL,'2026-11-18 11:03:43.089318'),('rbac_seed_version','4',NULL,'2026-11-18 11:03:43.060164'),('scheduler_status','{\"scanned\": true, \"last_tick_at\": \"2026-11-19T12:33:29.061642Z\"}',NULL,'2026-11-19 12:33:41.595199');
/*!40000 ALTER TABLE `system_settings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_assignments`
--

DROP TABLE IF EXISTS `task_assignments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_assignments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `assignee_id` bigint NOT NULL,
  `assigned_by_id` bigint NOT NULL,
  `assigned_at` datetime(6) NOT NULL,
  `unassigned_at` datetime(6) DEFAULT NULL,
  `reason` text,
  PRIMARY KEY (`id`),
  KEY `assigned_by_id` (`assigned_by_id`),
  KEY `ix_ta_assignee` (`assignee_id`,`unassigned_at`),
  KEY `ix_ta_task` (`task_id`),
  CONSTRAINT `task_assignments_ibfk_1` FOREIGN KEY (`assigned_by_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `task_assignments_ibfk_2` FOREIGN KEY (`assignee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `task_assignments_ibfk_3` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_assignments`
--

LOCK TABLES `task_assignments` WRITE;
/*!40000 ALTER TABLE `task_assignments` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_assignments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_attachments`
--

DROP TABLE IF EXISTS `task_attachments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_attachments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `uploaded_by_user_id` bigint NOT NULL,
  `original_name` varchar(255) NOT NULL,
  `stored_key` varchar(64) NOT NULL,
  `mime_type` varchar(100) NOT NULL,
  `size_bytes` int NOT NULL,
  `sha256` varchar(64) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `stored_key` (`stored_key`),
  KEY `uploaded_by_user_id` (`uploaded_by_user_id`),
  KEY `ix_att_task` (`task_id`),
  CONSTRAINT `task_attachments_ibfk_1` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`),
  CONSTRAINT `task_attachments_ibfk_2` FOREIGN KEY (`uploaded_by_user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_attachments`
--

LOCK TABLES `task_attachments` WRITE;
/*!40000 ALTER TABLE `task_attachments` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_attachments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_blocker_events`
--

DROP TABLE IF EXISTS `task_blocker_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_blocker_events` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `blocker_id` bigint NOT NULL,
  `actor_user_id` bigint DEFAULT NULL,
  `event` varchar(20) NOT NULL,
  `from_status` varchar(15) DEFAULT NULL,
  `to_status` varchar(15) DEFAULT NULL,
  `note` text,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `actor_user_id` (`actor_user_id`),
  KEY `ix_blke_blocker` (`blocker_id`,`created_at`),
  CONSTRAINT `task_blocker_events_ibfk_1` FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_blocker_events_ibfk_2` FOREIGN KEY (`blocker_id`) REFERENCES `task_blockers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_blocker_events`
--

LOCK TABLES `task_blocker_events` WRITE;
/*!40000 ALTER TABLE `task_blocker_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_blocker_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_blockers`
--

DROP TABLE IF EXISTS `task_blockers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_blockers` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `raised_by_user_id` bigint NOT NULL,
  `blocker_type` varchar(20) NOT NULL,
  `title` varchar(200) NOT NULL,
  `description` text NOT NULL,
  `impact` text,
  `blocks_work` tinyint(1) NOT NULL,
  `expected_resolution` text,
  `status` varchar(15) NOT NULL,
  `owner_user_id` bigint DEFAULT NULL,
  `attachment_id` bigint DEFAULT NULL,
  `opened_at` datetime(6) NOT NULL,
  `acknowledged_at` datetime(6) DEFAULT NULL,
  `resolved_at` datetime(6) DEFAULT NULL,
  `closed_at` datetime(6) DEFAULT NULL,
  `resolution_note` text,
  `escalated_to_leadership` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `attachment_id` (`attachment_id`),
  KEY `owner_user_id` (`owner_user_id`),
  KEY `raised_by_user_id` (`raised_by_user_id`),
  KEY `ix_blk_status` (`status`,`opened_at`),
  KEY `ix_blk_task` (`task_id`,`status`),
  CONSTRAINT `task_blockers_ibfk_1` FOREIGN KEY (`attachment_id`) REFERENCES `task_attachments` (`id`),
  CONSTRAINT `task_blockers_ibfk_2` FOREIGN KEY (`owner_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_blockers_ibfk_3` FOREIGN KEY (`raised_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_blockers_ibfk_4` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_blockers`
--

LOCK TABLES `task_blockers` WRITE;
/*!40000 ALTER TABLE `task_blockers` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_blockers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_categories`
--

DROP TABLE IF EXISTS `task_categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_categories` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(80) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_categories`
--

LOCK TABLES `task_categories` WRITE;
/*!40000 ALTER TABLE `task_categories` DISABLE KEYS */;
INSERT INTO `task_categories` VALUES (1,'Development',1),(2,'Bug fix',1),(3,'Design',1),(4,'Documentation',1),(5,'Marketing',1),(6,'HR',1),(7,'Sales',1),(8,'Support',1),(9,'Accounts',1),(10,'General',1);
/*!40000 ALTER TABLE `task_categories` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_comments`
--

DROP TABLE IF EXISTS `task_comments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_comments` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `author_user_id` bigint NOT NULL,
  `parent_id` bigint DEFAULT NULL,
  `kind` varchar(15) NOT NULL,
  `body` text NOT NULL,
  `attachment_id` bigint DEFAULT NULL,
  `edited_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `attachment_id` (`attachment_id`),
  KEY `author_user_id` (`author_user_id`),
  KEY `parent_id` (`parent_id`),
  KEY `ix_cmt_task` (`task_id`,`created_at`),
  CONSTRAINT `task_comments_ibfk_1` FOREIGN KEY (`attachment_id`) REFERENCES `task_attachments` (`id`),
  CONSTRAINT `task_comments_ibfk_2` FOREIGN KEY (`author_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_comments_ibfk_3` FOREIGN KEY (`parent_id`) REFERENCES `task_comments` (`id`),
  CONSTRAINT `task_comments_ibfk_4` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_comments`
--

LOCK TABLES `task_comments` WRITE;
/*!40000 ALTER TABLE `task_comments` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_comments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_completion_assurances`
--

DROP TABLE IF EXISTS `task_completion_assurances`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_completion_assurances` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `employee_id` bigint NOT NULL,
  `attempt_no` int NOT NULL,
  `summary` text NOT NULL,
  `tested` tinyint(1) NOT NULL,
  `test_notes` text,
  `evidence_url` varchar(500) DEFAULT NULL,
  `no_time_reason` text,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tca_attempt` (`task_id`,`attempt_no`),
  KEY `employee_id` (`employee_id`),
  CONSTRAINT `task_completion_assurances_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `task_completion_assurances_ibfk_2` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_completion_assurances`
--

LOCK TABLES `task_completion_assurances` WRITE;
/*!40000 ALTER TABLE `task_completion_assurances` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_completion_assurances` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_deadline_history`
--

DROP TABLE IF EXISTS `task_deadline_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_deadline_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `deadline_version` int NOT NULL,
  `previous_due_at` datetime(6) DEFAULT NULL,
  `new_due_at` datetime(6) NOT NULL,
  `changed_by_user_id` bigint NOT NULL,
  `change_type` varchar(20) NOT NULL,
  `reason` text,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tdh_version` (`task_id`,`deadline_version`),
  KEY `changed_by_user_id` (`changed_by_user_id`),
  CONSTRAINT `task_deadline_history_ibfk_1` FOREIGN KEY (`changed_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_deadline_history_ibfk_2` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_deadline_history`
--

LOCK TABLES `task_deadline_history` WRITE;
/*!40000 ALTER TABLE `task_deadline_history` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_deadline_history` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_delay_reasons`
--

DROP TABLE IF EXISTS `task_delay_reasons`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_delay_reasons` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `employee_id` bigint NOT NULL,
  `deadline_version` int NOT NULL,
  `kind` varchar(10) NOT NULL,
  `reason` text NOT NULL,
  `progress_pct` smallint NOT NULL,
  `work_completed` text NOT NULL,
  `remaining_work` text NOT NULL,
  `blockers_text` text,
  `expected_completion_at` datetime(6) NOT NULL,
  `attachment_id` bigint DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `attachment_id` (`attachment_id`),
  KEY `employee_id` (`employee_id`),
  KEY `ix_dr_task` (`task_id`,`created_at`),
  CONSTRAINT `task_delay_reasons_ibfk_1` FOREIGN KEY (`attachment_id`) REFERENCES `task_attachments` (`id`),
  CONSTRAINT `task_delay_reasons_ibfk_2` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `task_delay_reasons_ibfk_3` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`),
  CONSTRAINT `ck_dr_progress` CHECK ((`progress_pct` between 0 and 100))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_delay_reasons`
--

LOCK TABLES `task_delay_reasons` WRITE;
/*!40000 ALTER TABLE `task_delay_reasons` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_delay_reasons` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_delay_reviews`
--

DROP TABLE IF EXISTS `task_delay_reviews`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_delay_reviews` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `delay_reason_id` bigint NOT NULL,
  `reviewer_user_id` bigint NOT NULL,
  `decision` varchar(30) NOT NULL,
  `comment` text,
  `deadline_history_id` bigint DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `deadline_history_id` (`deadline_history_id`),
  KEY `reviewer_user_id` (`reviewer_user_id`),
  KEY `ix_task_delay_reviews_delay_reason_id` (`delay_reason_id`),
  CONSTRAINT `task_delay_reviews_ibfk_1` FOREIGN KEY (`deadline_history_id`) REFERENCES `task_deadline_history` (`id`),
  CONSTRAINT `task_delay_reviews_ibfk_2` FOREIGN KEY (`delay_reason_id`) REFERENCES `task_delay_reasons` (`id`),
  CONSTRAINT `task_delay_reviews_ibfk_3` FOREIGN KEY (`reviewer_user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_delay_reviews`
--

LOCK TABLES `task_delay_reviews` WRITE;
/*!40000 ALTER TABLE `task_delay_reviews` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_delay_reviews` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_head_ownership`
--

DROP TABLE IF EXISTS `task_head_ownership`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_head_ownership` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `employee_id` bigint NOT NULL,
  `user_id` bigint NOT NULL,
  `note` text,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_task_head_owner` (`task_id`,`employee_id`),
  KEY `employee_id` (`employee_id`),
  KEY `user_id` (`user_id`),
  KEY `ix_task_head_ownership_task_id` (`task_id`),
  CONSTRAINT `task_head_ownership_ibfk_1` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `task_head_ownership_ibfk_2` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`),
  CONSTRAINT `task_head_ownership_ibfk_3` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_head_ownership`
--

LOCK TABLES `task_head_ownership` WRITE;
/*!40000 ALTER TABLE `task_head_ownership` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_head_ownership` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_reverts`
--

DROP TABLE IF EXISTS `task_reverts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_reverts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `attempt_no` int NOT NULL,
  `reverted_by_user_id` bigint NOT NULL,
  `reason_code` varchar(25) NOT NULL,
  `reason` text NOT NULL,
  `found_by` varchar(60) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `bug_sheet_url` varchar(500) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `reverted_by_user_id` (`reverted_by_user_id`),
  KEY `ix_task_reverts_task_id` (`task_id`),
  KEY `ix_trv_reason` (`reason_code`,`created_at`),
  CONSTRAINT `task_reverts_ibfk_1` FOREIGN KEY (`reverted_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_reverts_ibfk_2` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_reverts`
--

LOCK TABLES `task_reverts` WRITE;
/*!40000 ALTER TABLE `task_reverts` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_reverts` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_status_history`
--

DROP TABLE IF EXISTS `task_status_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_status_history` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `from_status` varchar(20) DEFAULT NULL,
  `to_status` varchar(20) NOT NULL,
  `changed_by_user_id` bigint DEFAULT NULL,
  `reason` text,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `changed_by_user_id` (`changed_by_user_id`),
  KEY `ix_tsh_task` (`task_id`,`created_at`),
  CONSTRAINT `task_status_history_ibfk_1` FOREIGN KEY (`changed_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_status_history_ibfk_2` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_status_history`
--

LOCK TABLES `task_status_history` WRITE;
/*!40000 ALTER TABLE `task_status_history` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_status_history` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_time_corrections`
--

DROP TABLE IF EXISTS `task_time_corrections`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_time_corrections` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `employee_id` bigint NOT NULL,
  `time_log_id` bigint DEFAULT NULL,
  `kind` varchar(10) NOT NULL,
  `old_started_at` datetime(6) DEFAULT NULL,
  `old_ended_at` datetime(6) DEFAULT NULL,
  `new_started_at` datetime(6) NOT NULL,
  `new_ended_at` datetime(6) NOT NULL,
  `reason` text NOT NULL,
  `status` varchar(10) NOT NULL,
  `requested_by_user_id` bigint NOT NULL,
  `decided_by_user_id` bigint DEFAULT NULL,
  `decided_at` datetime(6) DEFAULT NULL,
  `decision_note` text,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `decided_by_user_id` (`decided_by_user_id`),
  KEY `requested_by_user_id` (`requested_by_user_id`),
  KEY `task_id` (`task_id`),
  KEY `time_log_id` (`time_log_id`),
  KEY `ix_tc_emp` (`employee_id`),
  KEY `ix_tc_status` (`status`,`created_at`),
  CONSTRAINT `task_time_corrections_ibfk_1` FOREIGN KEY (`decided_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_time_corrections_ibfk_2` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `task_time_corrections_ibfk_3` FOREIGN KEY (`requested_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_time_corrections_ibfk_4` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`),
  CONSTRAINT `task_time_corrections_ibfk_5` FOREIGN KEY (`time_log_id`) REFERENCES `task_time_logs` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_time_corrections`
--

LOCK TABLES `task_time_corrections` WRITE;
/*!40000 ALTER TABLE `task_time_corrections` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_time_corrections` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_time_logs`
--

DROP TABLE IF EXISTS `task_time_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_time_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `employee_id` bigint NOT NULL,
  `started_at` datetime(6) NOT NULL,
  `ended_at` datetime(6) DEFAULT NULL,
  `duration_seconds` int DEFAULT NULL,
  `source` varchar(15) NOT NULL,
  `end_reason` varchar(20) DEFAULT NULL,
  `status` varchar(10) NOT NULL,
  `confirmed` tinyint(1) NOT NULL,
  `continuous_since` datetime(6) DEFAULT NULL,
  `last_heartbeat_at` datetime(6) DEFAULT NULL,
  `note` text,
  `created_by_user_id` bigint DEFAULT NULL,
  `created_at` datetime(6) NOT NULL,
  `active_employee_key` bigint GENERATED ALWAYS AS ((case when ((`ended_at` is null) and (`status` = _utf8mb4'approved')) then `employee_id` end)) STORED,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_tl_one_active` (`active_employee_key`),
  KEY `created_by_user_id` (`created_by_user_id`),
  KEY `ix_tl_emp` (`employee_id`,`started_at`),
  KEY `ix_tl_task` (`task_id`),
  CONSTRAINT `task_time_logs_ibfk_1` FOREIGN KEY (`created_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_time_logs_ibfk_2` FOREIGN KEY (`employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `task_time_logs_ibfk_3` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`),
  CONSTRAINT `ck_tl_range` CHECK (((`ended_at` is null) or (`ended_at` >= `started_at`)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_time_logs`
--

LOCK TABLES `task_time_logs` WRITE;
/*!40000 ALTER TABLE `task_time_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_time_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_types`
--

DROP TABLE IF EXISTS `task_types`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_types` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(80) NOT NULL,
  `requires_review` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_types`
--

LOCK TABLES `task_types` WRITE;
/*!40000 ALTER TABLE `task_types` DISABLE KEYS */;
INSERT INTO `task_types` VALUES (1,'Task',0,1),(2,'Feature',0,1),(3,'Bug',0,1),(4,'Research',0,1),(5,'Review',1,1);
/*!40000 ALTER TABLE `task_types` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_updates`
--

DROP TABLE IF EXISTS `task_updates`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_updates` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `author_user_id` bigint NOT NULL,
  `progress_pct` smallint NOT NULL,
  `note` text NOT NULL,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `author_user_id` (`author_user_id`),
  KEY `ix_tu_task` (`task_id`,`created_at`),
  CONSTRAINT `task_updates_ibfk_1` FOREIGN KEY (`author_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `task_updates_ibfk_2` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`),
  CONSTRAINT `ck_tu_progress` CHECK ((`progress_pct` between 0 and 100))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_updates`
--

LOCK TABLES `task_updates` WRITE;
/*!40000 ALTER TABLE `task_updates` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_updates` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `task_verifications`
--

DROP TABLE IF EXISTS `task_verifications`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `task_verifications` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_id` bigint NOT NULL,
  `attempt_no` int NOT NULL,
  `verified_by_user_id` bigint NOT NULL,
  `note` text,
  `created_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `verified_by_user_id` (`verified_by_user_id`),
  KEY `ix_task_verifications_task_id` (`task_id`),
  CONSTRAINT `task_verifications_ibfk_1` FOREIGN KEY (`task_id`) REFERENCES `tasks` (`id`),
  CONSTRAINT `task_verifications_ibfk_2` FOREIGN KEY (`verified_by_user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `task_verifications`
--

LOCK TABLES `task_verifications` WRITE;
/*!40000 ALTER TABLE `task_verifications` DISABLE KEYS */;
/*!40000 ALTER TABLE `task_verifications` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tasks`
--

DROP TABLE IF EXISTS `tasks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tasks` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `task_no` varchar(40) NOT NULL,
  `title` varchar(200) NOT NULL,
  `description` text NOT NULL,
  `instructions` text,
  `project_id` bigint DEFAULT NULL,
  `department_id` bigint NOT NULL,
  `category_id` bigint DEFAULT NULL,
  `type_id` bigint DEFAULT NULL,
  `assignee_id` bigint NOT NULL,
  `assigned_by_id` bigint NOT NULL,
  `priority` varchar(10) NOT NULL,
  `priority_rank` smallint NOT NULL,
  `status` varchar(20) NOT NULL,
  `assigned_at` datetime(6) NOT NULL,
  `start_date` date DEFAULT NULL,
  `original_due_at` datetime(6) NOT NULL,
  `due_at` datetime(6) NOT NULL,
  `deadline_version` int NOT NULL,
  `extension_count` int NOT NULL,
  `estimated_seconds` int NOT NULL,
  `progress_pct` smallint NOT NULL,
  `requires_review` tinyint(1) NOT NULL,
  `acknowledged_at` datetime(6) DEFAULT NULL,
  `first_started_at` datetime(6) DEFAULT NULL,
  `completed_at` datetime(6) DEFAULT NULL,
  `cancelled_at` datetime(6) DEFAULT NULL,
  `cancel_reason` text,
  `version` int NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `submitted_at` datetime(6) DEFAULT NULL,
  `verified_at` datetime(6) DEFAULT NULL,
  `verified_by_user_id` bigint DEFAULT NULL,
  `revert_count` int NOT NULL,
  `status_before_block` varchar(20) DEFAULT NULL,
  `review_stage` varchar(12) DEFAULT NULL,
  `head_employee_id` bigint DEFAULT NULL,
  `qa_employee_id` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `task_no` (`task_no`),
  KEY `category_id` (`category_id`),
  KEY `type_id` (`type_id`),
  KEY `ix_task_assignee` (`assignee_id`,`status`,`due_at`),
  KEY `ix_task_assigner` (`assigned_by_id`),
  KEY `ix_task_dept` (`department_id`,`status`,`due_at`),
  KEY `ix_task_project` (`project_id`),
  KEY `ix_task_status_due` (`status`,`due_at`),
  KEY `fk_tasks_verified_by` (`verified_by_user_id`),
  KEY `fk_task_head` (`head_employee_id`),
  KEY `fk_task_qa` (`qa_employee_id`),
  CONSTRAINT `fk_task_head` FOREIGN KEY (`head_employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `fk_task_qa` FOREIGN KEY (`qa_employee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `fk_tasks_verified_by` FOREIGN KEY (`verified_by_user_id`) REFERENCES `users` (`id`),
  CONSTRAINT `tasks_ibfk_1` FOREIGN KEY (`assigned_by_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `tasks_ibfk_2` FOREIGN KEY (`assignee_id`) REFERENCES `employees` (`id`),
  CONSTRAINT `tasks_ibfk_3` FOREIGN KEY (`category_id`) REFERENCES `task_categories` (`id`),
  CONSTRAINT `tasks_ibfk_4` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`),
  CONSTRAINT `tasks_ibfk_5` FOREIGN KEY (`project_id`) REFERENCES `projects` (`id`),
  CONSTRAINT `tasks_ibfk_6` FOREIGN KEY (`type_id`) REFERENCES `task_types` (`id`),
  CONSTRAINT `ck_task_estimate` CHECK ((`estimated_seconds` > 0)),
  CONSTRAINT `ck_task_priority` CHECK ((`priority` in (_utf8mb4'critical',_utf8mb4'high',_utf8mb4'medium',_utf8mb4'low'))),
  CONSTRAINT `ck_task_progress` CHECK ((`progress_pct` between 0 and 100)),
  CONSTRAINT `ck_task_status` CHECK ((`status` in (_utf8mb4'assigned',_utf8mb4'acknowledged',_utf8mb4'in_progress',_utf8mb4'on_hold',_utf8mb4'blocked',_utf8mb4'under_review',_utf8mb4'completed',_utf8mb4'reopened',_utf8mb4'cancelled')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tasks`
--

LOCK TABLES `tasks` WRITE;
/*!40000 ALTER TABLE `tasks` DISABLE KEYS */;
/*!40000 ALTER TABLE `tasks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `timer_checkins`
--

DROP TABLE IF EXISTS `timer_checkins`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `timer_checkins` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `time_log_id` bigint NOT NULL,
  `kind` varchar(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `responded_at` datetime(6) DEFAULT NULL,
  `response` varchar(10) DEFAULT NULL,
  `note` text,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_checkin` (`time_log_id`,`kind`),
  CONSTRAINT `timer_checkins_ibfk_1` FOREIGN KEY (`time_log_id`) REFERENCES `task_time_logs` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `timer_checkins`
--

LOCK TABLES `timer_checkins` WRITE;
/*!40000 ALTER TABLE `timer_checkins` DISABLE KEYS */;
/*!40000 ALTER TABLE `timer_checkins` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `user_roles`
--

DROP TABLE IF EXISTS `user_roles`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user_roles` (
  `user_id` bigint NOT NULL,
  `role_id` bigint NOT NULL,
  `granted_by` bigint DEFAULT NULL,
  `granted_at` datetime(6) NOT NULL,
  PRIMARY KEY (`user_id`,`role_id`),
  KEY `granted_by` (`granted_by`),
  KEY `ix_user_roles_role` (`role_id`),
  CONSTRAINT `user_roles_ibfk_1` FOREIGN KEY (`granted_by`) REFERENCES `users` (`id`),
  CONSTRAINT `user_roles_ibfk_2` FOREIGN KEY (`role_id`) REFERENCES `roles` (`id`),
  CONSTRAINT `user_roles_ibfk_3` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user_roles`
--

LOCK TABLES `user_roles` WRITE;
/*!40000 ALTER TABLE `user_roles` DISABLE KEYS */;
INSERT INTO `user_roles` VALUES (1,1,NULL,'2026-11-18 11:03:43.359018');
/*!40000 ALTER TABLE `user_roles` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `email` varchar(255) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `must_change_password` tinyint(1) NOT NULL,
  `token_version` int NOT NULL,
  `failed_logins` int NOT NULL,
  `locked_until` datetime(6) DEFAULT NULL,
  `last_login_at` datetime(6) DEFAULT NULL,
  `timezone` varchar(64) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'krishadave485@gmail.com','$argon2id$v=19$m=65536,t=3,p=4$dwUvNSIbZZnGej6MVxgZFw$7myXQP895ownk/qnS9c9KSBz29Wf55L4NJc5MxTW4CA',1,0,0,0,NULL,'2026-11-19 12:26:35.394384','Asia/Kolkata','2026-11-18 11:03:43.353010','2026-11-19 12:26:35.398401');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `work_calendar_rules`
--

DROP TABLE IF EXISTS `work_calendar_rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `work_calendar_rules` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `weekday` smallint NOT NULL,
  `nth_in_month` smallint DEFAULT NULL,
  `is_working` tinyint(1) NOT NULL,
  `starts_at` time NOT NULL,
  `ends_at` time NOT NULL,
  `break_starts_at` time DEFAULT NULL,
  `break_ends_at` time DEFAULT NULL,
  `effective_from` date NOT NULL,
  `effective_to` date DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_wcr_weekday` (`weekday`)
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `work_calendar_rules`
--

LOCK TABLES `work_calendar_rules` WRITE;
/*!40000 ALTER TABLE `work_calendar_rules` DISABLE KEYS */;
INSERT INTO `work_calendar_rules` VALUES (1,0,NULL,1,'09:30:00','18:30:00','13:30:00','14:00:00','2000-01-01',NULL),(2,1,NULL,1,'09:30:00','18:30:00','13:30:00','14:00:00','2000-01-01',NULL),(3,2,NULL,1,'09:30:00','18:30:00','13:30:00','14:00:00','2000-01-01',NULL),(4,3,NULL,1,'09:30:00','18:30:00','13:30:00','14:00:00','2000-01-01',NULL),(5,4,NULL,1,'09:30:00','18:30:00','13:30:00','14:00:00','2000-01-01',NULL),(6,5,NULL,1,'09:30:00','18:30:00','13:30:00','14:00:00','2000-01-01',NULL),(7,6,NULL,0,'09:30:00','18:30:00','13:30:00','14:00:00','2000-01-01',NULL),(8,5,2,0,'09:30:00','18:30:00','13:30:00','14:00:00','2000-01-01',NULL),(9,5,4,0,'09:30:00','18:30:00','13:30:00','14:00:00','2000-01-01',NULL);
/*!40000 ALTER TABLE `work_calendar_rules` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'tms'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-19 18:26:44
