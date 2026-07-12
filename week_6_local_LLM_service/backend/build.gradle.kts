plugins {
    kotlin("jvm") version "2.1.0"
    kotlin("plugin.serialization") version "2.1.0"
    application
}

group = "com.witchercookbook"
version = "0.1.0"

repositories {
    mavenCentral()
}

val ktorVersion = "3.0.3"
val logbackVersion = "1.5.12"
val coroutinesVersion = "1.9.0"

dependencies {
    implementation("io.ktor:ktor-server-core:$ktorVersion")
    implementation("io.ktor:ktor-server-netty:$ktorVersion")
    implementation("io.ktor:ktor-server-content-negotiation:$ktorVersion")
    implementation("io.ktor:ktor-serialization-kotlinx-json:$ktorVersion")
    implementation("io.ktor:ktor-server-status-pages:$ktorVersion")
    implementation("io.ktor:ktor-server-call-logging:$ktorVersion")

    // HTTP client for talking to Ollama
    implementation("io.ktor:ktor-client-core:$ktorVersion")
    implementation("io.ktor:ktor-client-cio:$ktorVersion")
    implementation("io.ktor:ktor-client-content-negotiation:$ktorVersion")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:$coroutinesVersion")
    implementation("ch.qos.logback:logback-classic:$logbackVersion")

    testImplementation(kotlin("test"))
    testImplementation("io.ktor:ktor-server-test-host:$ktorVersion")
}

kotlin {
    jvmToolchain(21)
}

application {
    mainClass.set("com.witchercookbook.ApplicationKt")
}

tasks.test {
    useJUnitPlatform()
}

// Manual harness: ./gradlew chatHarness -Pprompt="Say hi"
// Requires `ollama serve` running with the chat model pulled.
tasks.register<JavaExec>("chatHarness") {
    group = "verification"
    description = "Calls OllamaClient.chat against a running Ollama and prints the completion."
    mainClass.set("com.witchercookbook.llm.OllamaClientHarnessKt")
    classpath = sourceSets["main"].runtimeClasspath
    javaLauncher.set(
        javaToolchains.launcherFor { languageVersion.set(JavaLanguageVersion.of(21)) }
    )
    (project.findProperty("prompt") as String?)?.let { args(it) }
}

// Manual harness: ./gradlew embedHarness -Ptext="venison stew"
// Requires `ollama serve` running with the embedding model pulled.
tasks.register<JavaExec>("embedHarness") {
    group = "verification"
    description = "Calls Embedder.embed against a running Ollama and prints the vector."
    mainClass.set("com.witchercookbook.llm.EmbedHarnessKt")
    classpath = sourceSets["main"].runtimeClasspath
    javaLauncher.set(
        javaToolchains.launcherFor { languageVersion.set(JavaLanguageVersion.of(21)) }
    )
    (project.findProperty("text") as String?)?.let { args(it) }
}
