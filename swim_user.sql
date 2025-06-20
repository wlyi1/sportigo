-- MySQL dump 10.13  Distrib 8.0.40, for macos14 (arm64)
--
-- Host: localhost    Database: swim
-- ------------------------------------------------------
-- Server version	9.0.1

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `user`
--

DROP TABLE IF EXISTS `user`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `user` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(80) NOT NULL,
  `email` varchar(120) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `user`
--

LOCK TABLES `user` WRITE;
/*!40000 ALTER TABLE `user` DISABLE KEYS */;
INSERT INTO `user` VALUES (1,'john_doe','john@example.com','scrypt:32768:8:1$8fDhQtfuSNl5hjtI$caa943c56d5737caea7514f622d15571ffdada8238ca5ea4fddcf4ea2682e82e7d751252afaac76703c1720ad8fb30063c30a637517d484c94e577439373b0db'),(2,'jane_smith','jane@example.com','scrypt:32768:8:1$JqoUr5NeinWtpSpF$546503f1fa59f8094d30df4ff0981fa7546625ad446ea15f152e7a089373173bcae4577f14e2a05c9b46d4a086f5af7bb3fc4a6f51b6198dd2c9d00982a9f368'),(3,'bob_wilson','bob@example.com','scrypt:32768:8:1$lP9v76DaoJLVyby9$9053aa631eaaed5fb2866d774ee19bc8221b7485476a1cc3d6efb487eae2e925b6a069d5992add761c709b45fc1bd0a1936bfa1a8923dad49a2550fabe663ecc'),(4,'gian','gian@gmail.com','scrypt:32768:8:1$LhPlAz4tTDAiC15e$47311ebf2900142faa086c31b9ac6b383819003b668e2ec055f0dff723cd733caa4c828f2a6d37d2410ca14f05134167c7474bd9e1228e625c41a89c26b5644c'),(5,'atlit2','atlit1@gmail.com','scrypt:32768:8:1$7oKUxYk4eeJrGDlG$cb6128ccb741c098ee2be6c09dae57701a66ad605e40ff1cf2bfd192e5d50f0ec3e3a6d05b4ef283aeb6e4c812f38eb710551f9d75a2ae0bbbac158734d698f5'),(6,'A','a@a','scrypt:32768:8:1$pnNZf5ZVrw54PBz8$a1cba24d4c84edd4f205705e075707c44d6e90da8e36f5f8dfbc4cea771e601d61a0c90b1b260f9ef9e9b9dd54d84d09c76dbdba544f46c04dd1f545eaec4020'),(7,'Aaa','aaa@aaa','scrypt:32768:8:1$GWvtmoCkvCSNTUMG$536e5c34bcecb217872412a3ac0178294a05bed7fe9745b73c5faed2a0e26b094da6d80287125598825e6261989fc365a0458700a4363e553af7fe26c6f090bf'),(8,'waliyudin','wali@gmail.com','scrypt:32768:8:1$8cHb98KsLOmrWk8s$93492a5d11f5d8ab866e4e4b4e70209361001c04173224efe3683590bf9f320cf25b3d157082e1f352752174567f2daa923fb5dab28e306d384ed3d195b6ad26'),(9,'superatlit','super@gmail.com','scrypt:32768:8:1$TcgZ40GJUpN9ZZRQ$c321d14aedb55a465f490cbb75e78b5af5aa188d30e67f9b421f5d7e8650905e8b730df28608d2980c2df4326f88f2f6513a7af71f6db6b569344e5e79257155'),(10,'123','123123@123.com','scrypt:32768:8:1$DBZURwiZ6GZdwX4Y$96936aaea311a36884808effbe00ac7acc543ba0c7d1c1ee4b7307334b47f2c1e63a17450df7b5f6df3cf7757e30d4e13ae4b61ee26e1f986b64d5981537d911');
/*!40000 ALTER TABLE `user` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-02-04 11:13:20
