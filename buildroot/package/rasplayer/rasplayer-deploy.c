#include <errno.h>
#include <fcntl.h>
#include <openssl/evp.h>
#include <openssl/pem.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef BUNDLE_DIR
#define BUNDLE_DIR "/home/dnl/work/rasplayer-update"
#endif
#ifndef PUBLIC_KEY
#define PUBLIC_KEY "/etc/rasplayer-update-public.pem"
#endif
#ifndef RELEASES_DIR
#define RELEASES_DIR "/opt/rasplayer/releases"
#endif
#ifndef CURRENT_LINK
#define CURRENT_LINK "/opt/rasplayer/current"
#endif
#ifndef PREVIOUS_LINK
#define PREVIOUS_LINK "/opt/rasplayer/previous"
#endif
#ifndef SERVICE_SCRIPT
#define SERVICE_SCRIPT "/etc/init.d/S50rasplayer"
#endif
#ifndef SERVICE_HELPER
#define SERVICE_HELPER "/usr/bin/rasplayer-service"
#endif
#ifndef SERVICE_HELPER_PREVIOUS
#define SERVICE_HELPER_PREVIOUS "/var/lib/rasplayer/deploy/rasplayer-service.previous"
#endif
#ifndef RUNTIME_DIR
#define RUNTIME_DIR "/run/rasplayer"
#endif
#define CONTROL_LOCK RUNTIME_DIR "/service-control.lock"
#define CONTROL_LOCK_PID CONTROL_LOCK "/pid"
#define MAX_MANIFEST 4096
#define MAX_APP_FILE (512 * 1024)
#define MAX_HELPER_FILE (256 * 1024)

static const char *const app_files[] = {
    "RasPlayer.py", "SoundPlayer.py", "SamplePlayer.py", "MusicPlayer.py",
    "OnlinePlayer.py", "SynthPlayer.py", "command_path.py", "systemd_notify.py"
};
#define APP_FILE_COUNT (sizeof(app_files) / sizeof(app_files[0]))

struct update_manifest {
    char release[65];
    unsigned char app_hashes[APP_FILE_COUNT][32];
    unsigned char helper_hash[32];
};

static int lock_held;

static void sleep_ms(unsigned int milliseconds)
{
    struct timespec delay = {
        .tv_sec = milliseconds / 1000U,
        .tv_nsec = (long)(milliseconds % 1000U) * 1000000L
    };
    while (nanosleep(&delay, &delay) != 0 && errno == EINTR) {
    }
}

static int process_alive(pid_t pid)
{
    char path[64];
    char line[256];
    FILE *file;

    if (pid <= 1 || kill(pid, 0) != 0) {
        return 0;
    }
    snprintf(path, sizeof(path), "/proc/%ld/status", (long)pid);
    file = fopen(path, "r");
    if (file == NULL) {
        return 0;
    }
    while (fgets(line, sizeof(line), file) != NULL) {
        if (strncmp(line, "State:", 6) == 0 && strchr(line, 'Z') != NULL) {
            fclose(file);
            return 0;
        }
    }
    fclose(file);
    return 1;
}

static int read_pid(const char *path, pid_t *pid)
{
    long value;
    FILE *file = fopen(path, "r");

    if (file == NULL || fscanf(file, "%ld", &value) != 1 || value <= 1) {
        if (file != NULL) {
            fclose(file);
        }
        return 0;
    }
    fclose(file);
    *pid = (pid_t)value;
    return 1;
}

static void release_lock(void)
{
    if (lock_held) {
        unlink(CONTROL_LOCK_PID);
        rmdir(CONTROL_LOCK);
        lock_held = 0;
    }
}

static int acquire_lock(void)
{
    unsigned int attempts = 0;

    while (mkdir(CONTROL_LOCK, 0700) != 0) {
        pid_t owner;
        if (errno != EEXIST) {
            fprintf(stderr, "deploy: cannot create control lock: %s\n", strerror(errno));
            return 0;
        }
        if (!read_pid(CONTROL_LOCK_PID, &owner) || !process_alive(owner)) {
            unlink(CONTROL_LOCK_PID);
            if (rmdir(CONTROL_LOCK) == 0 || errno == ENOENT) {
                continue;
            }
        }
        if (++attempts >= 100U) {
            fputs("deploy: service control is busy\n", stderr);
            return 0;
        }
        sleep_ms(100U);
    }
    lock_held = 1;
    {
        int fd = open(CONTROL_LOCK_PID, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        char text[32];
        int length;
        if (fd < 0) {
            release_lock();
            return 0;
        }
        length = snprintf(text, sizeof(text), "%ld\n", (long)getpid());
        if (write(fd, text, (size_t)length) != length) {
            close(fd);
            release_lock();
            return 0;
        }
        close(fd);
    }
    return 1;
}

static int read_regular_at(int directory, const char *name, size_t maximum,
                           unsigned char **data, size_t *length)
{
    struct stat status;
    int fd = openat(directory, name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    size_t offset = 0;

    if (fd < 0 || fstat(fd, &status) != 0 || !S_ISREG(status.st_mode) ||
        status.st_size < 0 || (uint64_t)status.st_size > maximum) {
        if (fd >= 0) close(fd);
        return 0;
    }
    *length = (size_t)status.st_size;
    *data = malloc(*length + 1U);
    if (*data == NULL) {
        close(fd);
        return 0;
    }
    while (offset < *length) {
        ssize_t count = read(fd, *data + offset, *length - offset);
        if (count <= 0) {
            free(*data);
            *data = NULL;
            close(fd);
            return 0;
        }
        offset += (size_t)count;
    }
    (*data)[*length] = '\0';
    close(fd);
    return 1;
}

static int secure_public_key(EVP_PKEY **key)
{
    struct stat status;
    FILE *file;

    if (lstat(PUBLIC_KEY, &status) != 0 || !S_ISREG(status.st_mode) ||
        status.st_uid != 0 || (status.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        fputs("deploy: missing or unsafe release public key\n", stderr);
        return 0;
    }
    file = fopen(PUBLIC_KEY, "r");
    if (file == NULL) return 0;
    *key = PEM_read_PUBKEY(file, NULL, NULL, NULL);
    fclose(file);
    if (*key == NULL || EVP_PKEY_base_id(*key) != EVP_PKEY_ED25519) {
        if (*key != NULL) EVP_PKEY_free(*key);
        *key = NULL;
        fputs("deploy: release key is not Ed25519\n", stderr);
        return 0;
    }
    return 1;
}

static int verify_signature(const unsigned char *manifest, size_t manifest_length,
                            const unsigned char *signature, size_t signature_length)
{
    EVP_PKEY *key = NULL;
    EVP_MD_CTX *context = NULL;
    int valid = 0;

    if (signature_length != 64U || !secure_public_key(&key)) return 0;
    context = EVP_MD_CTX_new();
    if (context != NULL && EVP_DigestVerifyInit(context, NULL, NULL, NULL, key) == 1 &&
        EVP_DigestVerify(context, signature, signature_length,
                         manifest, manifest_length) == 1) {
        valid = 1;
    }
    EVP_MD_CTX_free(context);
    EVP_PKEY_free(key);
    if (!valid) fputs("deploy: manifest signature verification failed\n", stderr);
    return valid;
}

static int decode_hash(const char *text, unsigned char output[32])
{
    size_t index;
    if (strlen(text) != 64U) return 0;
    for (index = 0; index < 32U; ++index) {
        unsigned int value;
        if (sscanf(text + index * 2U, "%2x", &value) != 1) return 0;
        output[index] = (unsigned char)value;
    }
    return 1;
}

static int safe_release(const char *release)
{
    size_t index;
    size_t length = strlen(release);
    if (length == 0 || length > 64U || release[0] == '.') return 0;
    for (index = 0; index < length; ++index) {
        char value = release[index];
        if (!((value >= 'a' && value <= 'z') || (value >= 'A' && value <= 'Z') ||
              (value >= '0' && value <= '9') || value == '.' || value == '_' || value == '-')) {
            return 0;
        }
    }
    return 1;
}

static int parse_hash_line(char *line, const char *expected, unsigned char hash[32])
{
    size_t name_length = strlen(expected);
    return strncmp(line, expected, name_length) == 0 && line[name_length] == '=' &&
           decode_hash(line + name_length + 1U, hash);
}

static int parse_manifest(unsigned char *data, struct update_manifest *result)
{
    char *save = NULL;
    char *line;
    size_t index;

    memset(result, 0, sizeof(*result));
    line = strtok_r((char *)data, "\n", &save);
    if (line == NULL || strcmp(line, "format=rasplayer-update-v1") != 0) return 0;
    line = strtok_r(NULL, "\n", &save);
    if (line == NULL || strncmp(line, "release=", 8) != 0 || !safe_release(line + 8)) return 0;
    strcpy(result->release, line + 8);
    for (index = 0; index < APP_FILE_COUNT; ++index) {
        line = strtok_r(NULL, "\n", &save);
        if (line == NULL || !parse_hash_line(line, app_files[index], result->app_hashes[index])) return 0;
    }
    line = strtok_r(NULL, "\n", &save);
    return line != NULL && parse_hash_line(line, "rasplayer-service", result->helper_hash) &&
           strtok_r(NULL, "\n", &save) == NULL;
}

static int copy_verified_at(int source_directory, const char *source_name,
                            int target_directory, const char *target_name,
                            mode_t mode, off_t maximum,
                            const unsigned char expected_hash[32])
{
    struct stat status;
    EVP_MD_CTX *context = NULL;
    unsigned char buffer[16384];
    unsigned char digest[EVP_MAX_MD_SIZE];
    unsigned int digest_length = 0;
    int source = -1;
    int target = -1;
    int success = 0;

    source = openat(source_directory, source_name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (source < 0 || fstat(source, &status) != 0 || !S_ISREG(status.st_mode) ||
        status.st_size < 0 || status.st_size > maximum) goto done;
    target = openat(target_directory, target_name,
                    O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, mode);
    if (target < 0) goto done;
    context = EVP_MD_CTX_new();
    if (context == NULL || EVP_DigestInit_ex(context, EVP_sha256(), NULL) != 1) goto done;
    while (1) {
        ssize_t count = read(source, buffer, sizeof(buffer));
        size_t offset = 0;
        if (count < 0) goto done;
        if (count == 0) break;
        if (EVP_DigestUpdate(context, buffer, (size_t)count) != 1) goto done;
        while (offset < (size_t)count) {
            ssize_t written = write(target, buffer + offset, (size_t)count - offset);
            if (written <= 0) goto done;
            offset += (size_t)written;
        }
    }
    if (EVP_DigestFinal_ex(context, digest, &digest_length) != 1 || digest_length != 32U ||
        memcmp(digest, expected_hash, 32U) != 0 || fchown(target, 0, 0) != 0 ||
        fchmod(target, mode) != 0 || fsync(target) != 0) goto done;
    success = 1;
done:
    EVP_MD_CTX_free(context);
    if (source >= 0) close(source);
    if (target >= 0) close(target);
    if (!success) unlinkat(target_directory, target_name, 0);
    return success;
}

static int run_service(const char *action)
{
    pid_t child = fork();
    int status = 0;
    pid_t waited;
    if (child < 0) return 0;
    if (child == 0) {
        char *const arguments[] = {(char *)SERVICE_SCRIPT, (char *)action, NULL};
        char *const environment[] = {
            (char *)"PATH=/usr/sbin:/usr/bin:/sbin:/bin",
            (char *)"HOME=/root", (char *)"USER=root", (char *)"LOGNAME=root",
            (char *)"RASPLAYER_CONTROL_LOCK_HELD=1", NULL
        };
        execve(SERVICE_SCRIPT, arguments, environment);
        _exit(126);
    }
    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    return waited == child && WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

static int healthy_within(unsigned int seconds)
{
    unsigned int checks = seconds * 10U;
    while (checks-- > 0U) {
        pid_t manager;
        pid_t child;
        if (access(RUNTIME_DIR "/ready", F_OK) == 0 &&
            read_pid(RUNTIME_DIR "/manager.pid", &manager) && process_alive(manager) &&
            read_pid(RUNTIME_DIR "/rasplayer.pid", &child) && process_alive(child)) {
            return 1;
        }
        sleep_ms(100U);
    }
    return 0;
}

static int read_link_target(const char *path, char target[256])
{
    ssize_t length = readlink(path, target, 255U);
    if (length <= 0 || length >= 255) return 0;
    target[length] = '\0';
    return strncmp(target, RELEASES_DIR "/", strlen(RELEASES_DIR) + 1U) == 0;
}

static int atomic_link(const char *target, const char *path)
{
    char temporary[320];
    snprintf(temporary, sizeof(temporary), "%s.new.%ld", path, (long)getpid());
    unlink(temporary);
    if (symlink(target, temporary) != 0 || rename(temporary, path) != 0) {
        unlink(temporary);
        return 0;
    }
    return 1;
}

static int swap_helper(void)
{
    char temporary[256];
    struct stat status;
    if (lstat(SERVICE_HELPER_PREVIOUS, &status) != 0) return 0;
    snprintf(temporary, sizeof(temporary), "/usr/bin/.rasplayer-service.swap.%ld", (long)getpid());
    unlink(temporary);
    if (rename(SERVICE_HELPER, temporary) != 0) return 0;
    if (rename(SERVICE_HELPER_PREVIOUS, SERVICE_HELPER) != 0) {
        rename(temporary, SERVICE_HELPER);
        return 0;
    }
    if (rename(temporary, SERVICE_HELPER_PREVIOUS) != 0) return 0;
    return 1;
}

static void remove_release_temp(const char *path)
{
    size_t index;
    char file[384];
    for (index = 0; index < APP_FILE_COUNT; ++index) {
        snprintf(file, sizeof(file), "%s/%s", path, app_files[index]);
        unlink(file);
    }
    snprintf(file, sizeof(file), "%s/Sounds", path);
    unlink(file);
    rmdir(path);
}

static int apply_update(void)
{
    unsigned char *manifest_data = NULL;
    unsigned char *signature = NULL;
    size_t manifest_length = 0;
    size_t signature_length = 0;
    struct update_manifest manifest;
    char manifest_parse[MAX_MANIFEST + 1];
    char temporary_release[320] = "";
    char final_release[256];
    char old_release[256];
    char helper_temp[256];
    int bundle = -1;
    int payload = -1;
    int release_fd = -1;
    int usr_bin = -1;
    int helper_prepared = 0;
    int helper_installed = 0;
    int switched = 0;
    int success = 0;
    size_t index;

    bundle = open(BUNDLE_DIR, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (bundle < 0 || !read_regular_at(bundle, "manifest", MAX_MANIFEST,
                                        &manifest_data, &manifest_length) ||
        !read_regular_at(bundle, "signature", 128, &signature, &signature_length) ||
        !verify_signature(manifest_data, manifest_length, signature, signature_length)) {
        goto done;
    }
    memcpy(manifest_parse, manifest_data, manifest_length + 1U);
    if (!parse_manifest((unsigned char *)manifest_parse, &manifest)) {
        fputs("deploy: invalid or non-allowlisted manifest\n", stderr);
        goto done;
    }
    payload = openat(bundle, "payload", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (payload < 0) goto done;
    snprintf(final_release, sizeof(final_release), RELEASES_DIR "/%s", manifest.release);
    snprintf(temporary_release, sizeof(temporary_release), RELEASES_DIR "/.%s.tmp.%ld",
             manifest.release, (long)getpid());
    if (mkdir(temporary_release, 0700) != 0) {
        fputs("deploy: release already exists or cannot be created\n", stderr);
        goto done;
    }
    release_fd = open(temporary_release, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    if (release_fd < 0) goto done;
    for (index = 0; index < APP_FILE_COUNT; ++index) {
        mode_t mode = index == 0 ? 0755 : 0644;
        if (!copy_verified_at(payload, app_files[index], release_fd, app_files[index],
                              mode, MAX_APP_FILE, manifest.app_hashes[index])) {
            fprintf(stderr, "deploy: payload verification failed for %s\n", app_files[index]);
            goto done;
        }
    }
    {
        char sounds[384];
        snprintf(sounds, sizeof(sounds), "%s/Sounds", temporary_release);
        unlink(sounds);
        if (symlink("/home/dnl/RasPlayer/Sounds", sounds) != 0) goto done;
    }
    if (fchmod(release_fd, 0755) != 0 || fsync(release_fd) != 0) goto done;

    usr_bin = open("/usr/bin", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    snprintf(helper_temp, sizeof(helper_temp), ".rasplayer-service.new.%ld", (long)getpid());
    if (usr_bin < 0 || !copy_verified_at(payload, "rasplayer-service", usr_bin,
                                          helper_temp, 04755, MAX_HELPER_FILE,
                                          manifest.helper_hash)) goto done;
    helper_prepared = 1;
    close(release_fd);
    release_fd = -1;
    if (rename(temporary_release, final_release) != 0) goto done;
    temporary_release[0] = '\0';

    if (!acquire_lock() || !run_service("stop") || !read_link_target(CURRENT_LINK, old_release)) goto done;
    if (!atomic_link(old_release, PREVIOUS_LINK) || !atomic_link(final_release, CURRENT_LINK)) goto done;
    switched = 1;
    unlink(SERVICE_HELPER_PREVIOUS);
    if (rename(SERVICE_HELPER, SERVICE_HELPER_PREVIOUS) != 0 ||
        renameat(usr_bin, helper_temp, AT_FDCWD, SERVICE_HELPER) != 0) {
        rename(SERVICE_HELPER_PREVIOUS, SERVICE_HELPER);
        goto rollback;
    }
    helper_installed = 1;
    if (!run_service("start") || !healthy_within(20U)) goto rollback;
    printf("deploy: release=%s active previous=%s\n", manifest.release, old_release);
    success = 1;
    goto done;

rollback:
    fputs("deploy: health check failed; rolling back\n", stderr);
    run_service("stop");
    if (switched) atomic_link(old_release, CURRENT_LINK);
    if (helper_installed) swap_helper();
    run_service("start");
    healthy_within(20U);
done:
    if (!success && lock_held && access(RUNTIME_DIR "/manager.pid", F_OK) != 0) {
        run_service("start");
    }
    if (release_fd >= 0) close(release_fd);
    if (usr_bin >= 0) {
        if (!success && helper_prepared && !helper_installed) unlinkat(usr_bin, helper_temp, 0);
        close(usr_bin);
    }
    if (temporary_release[0] != '\0') remove_release_temp(temporary_release);
    if (payload >= 0) close(payload);
    if (bundle >= 0) close(bundle);
    free(manifest_data);
    free(signature);
    release_lock();
    return success ? 0 : 1;
}

static int rollback_update(void)
{
    char current[256];
    char previous[256];
    int helper_swapped = 0;

    if (!acquire_lock() || !read_link_target(CURRENT_LINK, current) ||
        !read_link_target(PREVIOUS_LINK, previous) || !run_service("stop")) {
        release_lock();
        return 1;
    }
    if (!atomic_link(previous, CURRENT_LINK)) {
        run_service("start");
        release_lock();
        return 1;
    }
    if (!atomic_link(current, PREVIOUS_LINK)) {
        atomic_link(current, CURRENT_LINK);
        run_service("start");
        release_lock();
        return 1;
    }
    helper_swapped = swap_helper();
    if (!run_service("start") || !healthy_within(20U)) {
        fputs("rollback: previous release failed health check; restoring current release\n", stderr);
        run_service("stop");
        atomic_link(current, CURRENT_LINK);
        atomic_link(previous, PREVIOUS_LINK);
        if (helper_swapped) swap_helper();
        run_service("start");
        healthy_within(20U);
        release_lock();
        return 1;
    }
    printf("rollback: active=%s previous=%s\n", previous, current);
    release_lock();
    return 0;
}

int main(int argc, char **argv)
{
    if (getuid() != 0 || geteuid() != 0 || argc != 2) return 126;
    atexit(release_lock);
    if (strcmp(argv[1], "deploy") == 0) return apply_update();
    if (strcmp(argv[1], "rollback") == 0) return rollback_update();
    return 2;
}
